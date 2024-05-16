FROM base:latest

COPY smooth_server.zip app/
COPY flow_server.zip app/
COPY cumsum_server.zip app/

COPY processing_container.sh app/
RUN chmod +x app/processing_container.sh
CMD ./app/processing_container.sh