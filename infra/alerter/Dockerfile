FROM python:3.12-alpine
RUN pip install --no-cache-dir requests
COPY alerter.py /alerter.py
CMD ["python", "/alerter.py"]
