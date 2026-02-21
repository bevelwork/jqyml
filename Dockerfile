# jqyml: jq-based YAML parser service (HTTP)
FROM alpine:3.19
RUN apk add --no-cache jq python3
WORKDIR /app
COPY yaml.jq run.jq index.jq server.py /app/
EXPOSE 8888
CMD ["python3", "/app/server.py"]
