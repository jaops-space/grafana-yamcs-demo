# Grafana Yamcs Demo Docker setup

This folder runs Yamcs and the demo simulator in Docker.

## Prerequisites

* make
* docker
* docker-compose

## Running

Start everything:

    docker compose up --build

or with Make:

    make demo-up

Yamcs: http://localhost:8090

Generated images: http://localhost:8091

Stop everything:

    make demo-down
