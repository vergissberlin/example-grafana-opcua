FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir asyncua==1.1.5 prometheus-client==0.20.0
COPY exporter.py .
EXPOSE 9686
CMD ["python", "exporter.py"]
