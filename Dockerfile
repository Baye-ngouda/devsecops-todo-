# Dockerfile volontairement mal configuré (challenge)
FROM python:3.8
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
ENV DB_PASSWORD=SuperSecret123
EXPOSE 5000
CMD ["python", "app.py"]
