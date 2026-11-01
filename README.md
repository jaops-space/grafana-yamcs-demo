# Grafana Yamcs Demo

This repository holds a Yamcs demo application for the JAOPS Grafana Yamcs plugin.

It is based on the Yamcs quickstart spacecraft simulation, but extended for Grafana integration testing and demos:

* realtime and historical CCSDS telemetry
* units, thresholds and parameter alarms
* scalar, enum, boolean, string, aggregate and array parameter types
* arrays of aggregates, aggregates of arrays and nested aggregates
* local image URL telemetry for image-panel demos
* Yamcs events
* richer command metadata with arguments, constraints and verifiers


## Prerequisites

For the easiest setup:

* Docker
* Docker Compose

For native development:

* Java 17+
* Python 3.10+
* Linux x64/aarch64, macOS x64/aarch64, or Windows x64


## Run the demo

Start Yamcs and the simulator:

    cd docker
    docker compose up --build

Open Yamcs at:

    http://localhost:8090

The simulator sends CCSDS packets to Yamcs, publishes local feature/image parameters, and creates demo events.

Generated image frames are served at:

    http://localhost:8091


## Instance and MDB

The Yamcs instance is named:

    demo

The loaded space systems are:

* `/myproject` - the original spacecraft quickstart telemetry and commands
* `/features` - local parameters covering Grafana/Yamcs integration-test edge cases
* `/images` - local parameters for generated demo image URLs


## Native development

Compile this project:

    ./mvnw compile

Start Yamcs on localhost:

    ./mvnw org.yamcs:yamcs-maven-plugin:1.3.5:run

Start the simulator:

    python simulator.py

The simulator sends packets at 1 Hz over UDP to Yamcs. There is enough test data to run for a full calendar day.

This project defines example CCSDS telecommands. They are sent to UDP port 10025 by default. Set `YAMCS_TC_HOST` and `YAMCS_TC_PORT` on Yamcs to route commands through a different host or published port; this does not change the simulator's listening port. The simulator counts received commands.


## Bundling

Running through Maven is useful during development, but it is not recommended for production environments. Instead bundle up your Yamcs application in a tar.gz file:

    ./mvnw package
