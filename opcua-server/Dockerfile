FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir asyncua==1.1.5
COPY server.py .
EXPOSE 4840
CMD ["python", "server.py"]
