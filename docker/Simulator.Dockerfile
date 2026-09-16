FROM python:3.12-slim

WORKDIR /demo

COPY simulator.py /demo/simulator.py
COPY testdata.ccsds /demo/testdata.ccsds

EXPOSE 8091

CMD ["python", "/demo/simulator.py", "--tm_host", "yamcs", "--tc_host", "0.0.0.0", "--yamcs_url", "http://yamcs:8090"]
