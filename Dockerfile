# jqyml: jq-based YAML parser service (HTTP)
FROM alpine:3.19
RUN apk add --no-cache jq python3 py3-yaml curl
WORKDIR /app
COPY yaml.jq log.jq run.jq index.jq index.jqx header.jqx head.jqx empty.jqx index_old.jq jqx.jq 404.jqx 400.jqx 401.jqx built_with.jqx built_with.jq rule110.jq rule110.jqx fizzbuzz.jq fizzbuzz.jqx doom.jqx parse.jq state.jq server.py favicon.ico /app/
COPY doom_jq/ /app/doom_jq/
COPY state/ /app/state/
EXPOSE 8888
CMD ["python3", "/app/server.py"]
