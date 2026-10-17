limit_conn perip ${CONN_PER_IP};
proxy_read_timeout ${PROXY_TIMEOUT};
proxy_send_timeout ${PROXY_TIMEOUT};
proxy_buffering on;
proxy_buffer_size 32k;
proxy_buffers 16 32k;
proxy_busy_buffers_size 64k;
