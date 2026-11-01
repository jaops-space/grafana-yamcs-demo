#!/usr/bin/env python3

import binascii
import io
import json
import os
import socket
import sys
import argparse
import urllib.error
import urllib.parse
import urllib.request

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from struct import unpack_from
from threading import Thread
from time import sleep

parser = argparse.ArgumentParser(description='Yamcs Simulator')
parser.add_argument('--testdata', type=str, default='testdata.ccsds', help='simulated testdata.ccsds data')

# telemetry
parser.add_argument('--tm_host',    type=str, default='127.0.0.1', help='TM host')
parser.add_argument('--tm_port',    type=int, default=10015,       help='TM port')
parser.add_argument('-r', '--rate', type=int, default=1,           help='TM playback rate. 1 = 1Hz, 10 = 10Hz, etc.')

# telecommand
parser.add_argument('--tc_host', type=str, default='127.0.0.1', help='TC host')
parser.add_argument('--tc_port', type=int, default=10025 ,      help='TC port')

# Yamcs local-parameter/image/event publishing
parser.add_argument('--yamcs_url', type=str, default='http://127.0.0.1:8090', help='Yamcs base URL')
parser.add_argument('--yamcs_instance', type=str, default='demo', help='Yamcs instance')
parser.add_argument('--yamcs_processor', type=str, default='realtime', help='Yamcs processor')
parser.add_argument('--image_dir', type=str, default='simulator/images/generated', help='directory for generated image frames')
parser.add_argument('--image_public_base_url', type=str, default='http://127.0.0.1:8091', help='public URL for generated images')
parser.add_argument('--image_port', type=int, default=8091, help='HTTP port for generated images')
parser.add_argument('--image_rate', type=float, default=2.0, help='generated image rate in Hz')
parser.add_argument('--disable_local_parameters', action='store_true', help='disable Yamcs local-parameter/event/image publishing')

args = vars(parser.parse_args())

# test data
TEST_DATA = args['testdata']

# telemetry
TM_SEND_ADDRESS = args['tm_host']
TM_SEND_PORT    = args['tm_port']
RATE            = args['rate']

# telecommand
TC_RECEIVE_ADDRESS = args['tc_host']
TC_RECEIVE_PORT    = args['tc_port']

YAMCS_URL       = args['yamcs_url'].rstrip('/')
YAMCS_INSTANCE  = args['yamcs_instance']
YAMCS_PROCESSOR = args['yamcs_processor']
IMAGE_DIR       = Path(args['image_dir'])
IMAGE_BASE_URL  = args['image_public_base_url'].rstrip('/')
IMAGE_PORT      = args['image_port']
IMAGE_RATE      = args['image_rate']
LOCAL_ENABLED   = not args['disable_local_parameters']

def yamcs_value_string(value):
    return {'type': 'STRING', 'stringValue': str(value)}


def yamcs_value_uint32(value):
    return {'type': 'UINT32', 'uint32Value': int(value)}


def yamcs_value_double(value):
    return {'type': 'DOUBLE', 'doubleValue': float(value)}


def yamcs_value_bool(value):
    return {'type': 'BOOLEAN', 'booleanValue': bool(value)}


def yamcs_value_enum(label, number):
    # Local parameter conversion accepts enum labels as strings (or integer raw
    # values). The protobuf ENUMERATED shape is what Yamcs returns to clients,
    # but it is not accepted as an input value for typed local parameters.
    return yamcs_value_string(label)


def yamcs_value_array(values):
    return {'type': 'ARRAY', 'arrayValue': values}


def yamcs_value_aggregate(**members):
    return {
        'type': 'AGGREGATE',
        'aggregateValue': {
            'name': list(members.keys()),
            'value': list(members.values()),
        },
    }


def yamcs_parameter_url(parameter):
    encoded = '/'.join(urllib.parse.quote(part, safe='') for part in parameter.split('/'))
    return f'{YAMCS_URL}/api/processors/{YAMCS_INSTANCE}/{YAMCS_PROCESSOR}/parameters{encoded}'


def put_local_parameter(parameter, value):
    body = json.dumps(value).encode('utf-8')
    request = urllib.request.Request(
        yamcs_parameter_url(parameter),
        data=body,
        method='PUT',
        headers={'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(request, timeout=2):
        pass


def post_event(message, severity='info', event_type='demo'):
    body = json.dumps({
        'source': 'grafana-yamcs-demo',
        'type': event_type,
        'severity': severity,
        'message': message,
    }).encode('utf-8')
    request = urllib.request.Request(
        f'{YAMCS_URL}/api/archive/{YAMCS_INSTANCE}/events',
        data=body,
        method='POST',
        headers={'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(request, timeout=2):
        pass


def try_yamcs_write(description, fn):
    while True:
        try:
            fn()
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            sys.stdout.write(f'\nWaiting to publish {description}: {e}\n')
            sys.stdout.flush()
            sleep(1)


def generate_demo_svg(path, frame_number):
    # Lightweight placeholder until a project-specific base image is provided.
    # The image number is intentionally large and centered for testing cache and
    # refresh behavior in the Grafana image panel.
    hue = (frame_number * 23) % 360
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  <defs>
    <linearGradient id="sky" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0%" stop-color="hsl({hue}, 55%, 28%)"/>
      <stop offset="100%" stop-color="hsl({(hue + 45) % 360}, 45%, 10%)"/>
    </linearGradient>
  </defs>
  <rect width="1280" height="720" fill="url(#sky)"/>
  <g opacity="0.18" stroke="white" stroke-width="2">
    <path d="M0 530 H1280"/>
    <path d="M160 720 L540 360"/>
    <path d="M1120 720 L740 360"/>
    <path d="M320 720 L590 360"/>
    <path d="M960 720 L690 360"/>
  </g>
  <text x="640" y="335" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-size="82" font-weight="800" fill="white">image {frame_number:04d}</text>
  <text x="640" y="392" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-size="30" fill="rgba(255,255,255,0.82)">grafana-yamcs-demo generated camera frame</text>
</svg>
'''
    path.write_text(svg, encoding='utf-8')


def serve_images():
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    handler = partial(SimpleHTTPRequestHandler, directory=str(IMAGE_DIR))
    server = ThreadingHTTPServer(('0.0.0.0', IMAGE_PORT), handler)
    server.serve_forever()


def send_tm(simulator):
    tm_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    with io.open(TEST_DATA, 'rb') as f:
        simulator.tm_counter = 1
        header = bytearray(6)
        while f.readinto(header) == 6:
            (len,) = unpack_from('>H', header, 4)

            packet = bytearray(len + 7)
            f.seek(-6, io.SEEK_CUR)
            f.readinto(packet)

            try_yamcs_write(
                'telemetry packet',
                lambda: tm_socket.sendto(packet, (TM_SEND_ADDRESS, TM_SEND_PORT)),
            )
            simulator.tm_counter += 1

            sleep(1 / simulator.rate)


def receive_tc(simulator):
    tc_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tc_socket.bind((TC_RECEIVE_ADDRESS, TC_RECEIVE_PORT ))
    while True:
        data, _ = tc_socket.recvfrom(4096)
        simulator.last_tc = data
        simulator.tc_counter += 1


def publish_local_parameters(simulator):
    if not LOCAL_ENABLED:
        return

    image_interval = 1 / max(IMAGE_RATE, 0.1)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    image_thread = Thread(target=serve_images)
    image_thread.daemon = True
    image_thread.start()

    frame_number = 0
    event_number = 0
    while True:
        frame_number += 1
        image_name = f'image-{frame_number:04d}.svg'
        image_path = IMAGE_DIR / image_name
        generate_demo_svg(image_path, frame_number)
        image_url = f'{IMAGE_BASE_URL}/{image_name}'

        mode_index = frame_number % 6
        mode_labels = ['BOOT', 'SAFE', 'NOMINAL', 'PAYLOAD', 'DOWNLINK', 'FAULT']
        mode = mode_labels[mode_index]
        voltage = 30.5 + ((frame_number % 16) - 8) * 0.08
        current = 2.5 + (frame_number % 9) * 0.35
        temp = 22.0 + (frame_number % 20) * 0.7

        def publish():
            put_local_parameter('/images/url_storage', yamcs_value_string(image_name))
            put_local_parameter('/images/url_full', yamcs_value_string(image_url))
            put_local_parameter('/images/number', yamcs_value_uint32(frame_number))

            put_local_parameter('/features/DemoCounter', yamcs_value_uint32(frame_number))
            put_local_parameter('/features/DemoMode', yamcs_value_enum(mode, mode_index))
            put_local_parameter('/features/DemoMessage', yamcs_value_string(f'Demo frame {frame_number}'))
            put_local_parameter('/features/DemoEnabled', yamcs_value_bool(mode != 'FAULT'))
            put_local_parameter('/features/DemoVoltage', yamcs_value_double(voltage))
            put_local_parameter('/features/DemoCurrent', yamcs_value_double(current))
            put_local_parameter('/features/DemoTemperature', yamcs_value_double(temp))
            put_local_parameter('/features/DemoCellVoltages', yamcs_value_array([
                yamcs_value_double(3.75 + 0.01 * ((frame_number + i) % 8)) for i in range(8)
            ]))
            put_local_parameter('/features/DemoPowerMatrix', yamcs_value_array([
                yamcs_value_double(current + row + col * 0.1)
                for row in range(2)
                for col in range(4)
            ]))
            channel = lambda idx: yamcs_value_aggregate(
                voltage=yamcs_value_double(voltage - idx * 0.1),
                current=yamcs_value_double(current + idx * 0.25),
                temperature=yamcs_value_double(temp + idx),
                enabled=yamcs_value_bool(idx != 3 or mode != 'FAULT'),
                healthy=yamcs_value_bool(mode != 'FAULT'),
            )
            channels = [channel(i) for i in range(4)]
            put_local_parameter('/features/DemoPowerChannels', yamcs_value_array(channels))
            put_local_parameter('/features/DemoBundle', yamcs_value_aggregate(
                mode=yamcs_value_enum(mode, mode_index),
                position=yamcs_value_aggregate(
                    x=yamcs_value_double(7000000 + frame_number),
                    y=yamcs_value_double(1000 + frame_number * 2),
                    z=yamcs_value_double(500 + frame_number * 3),
                ),
                attitude=yamcs_value_aggregate(
                    roll=yamcs_value_double((frame_number % 30) - 15),
                    pitch=yamcs_value_double((frame_number % 20) - 10),
                    yaw=yamcs_value_double((frame_number * 7) % 360),
                ),
                battery=yamcs_value_aggregate(
                    stateOfCharge=yamcs_value_double(max(15, 96 - frame_number % 100)),
                    cells=yamcs_value_array([yamcs_value_double(3.75 + 0.01 * ((frame_number + i) % 8)) for i in range(8)]),
                    temperatures=yamcs_value_array([yamcs_value_double(temp + i) for i in range(4)]),
                ),
                powerChannels=yamcs_value_array(channels),
            ))

        try_yamcs_write('local parameters', publish)

        if frame_number == 1 or frame_number % 30 == 0:
            event_number += 1
            severity = 'warning' if mode == 'FAULT' else 'info'
            try_yamcs_write('demo event', lambda: post_event(f'Demo event {event_number}: mode={mode}', severity=severity))

        sleep(image_interval)


class Simulator():

    def __init__(self, rate):
        self.tm_counter = 0
        self.tc_counter = 0
        self.tm_thread = None
        self.tc_thread = None
        self.local_thread = None
        self.last_tc = None
        self.rate = rate

    def start(self):
        self.tm_thread = Thread(target=send_tm, args=(self,))
        self.tm_thread.daemon = True
        self.tm_thread.start()
        self.tc_thread = Thread(target=receive_tc, args=(self,))
        self.tc_thread.daemon = True
        self.tc_thread.start()
        self.local_thread = Thread(target=publish_local_parameters, args=(self,))
        self.local_thread.daemon = True
        self.local_thread.start()

    def print_status(self):
        cmdhex = None
        if self.last_tc:
            cmdhex = binascii.hexlify(self.last_tc).decode('ascii')
        return 'Sent: {} packets. Received: {} commands. Last command: {}'.format(
                         self.tm_counter, self.tc_counter, cmdhex)


if __name__ == '__main__':
    simulator = Simulator(RATE)
    simulator.start()
    sys.stdout.write('Using playback rate of ' + str(RATE) + 'Hz, ');
    sys.stdout.write('TM host=' + str(TM_SEND_ADDRESS) + ', TM port=' + str(TM_SEND_PORT) + ', ');
    sys.stdout.write('TC host=' + str(TC_RECEIVE_ADDRESS) + ', TC port=' + str(TC_RECEIVE_PORT) + '\r\n');
    if LOCAL_ENABLED:
        sys.stdout.write('Publishing local parameters/events to ' + YAMCS_URL + ' and images from ' + str(IMAGE_DIR) + '\r\n')
    try:
        prev_status = None
        while True:
            status = simulator.print_status()
            if status != prev_status:
                sys.stdout.write('\r')
                sys.stdout.write(status)
                sys.stdout.flush()
                prev_status = status
            sleep(0.5)
    except KeyboardInterrupt:
        sys.stdout.write('\n')
        sys.stdout.flush()
