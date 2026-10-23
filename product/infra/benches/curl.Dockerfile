FROM alpine:3.24@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6 AS build
RUN apk add --no-cache build-base perl gnutls-dev nghttp2-dev nghttp3-dev ngtcp2-dev zlib-dev zstd-dev brotli-dev
ADD --checksum=sha256:8dadd7d2536a314f982ad05a651b713f426bf7d02cc2c76cffb9796f2218e6c5 https://curl.se/download/curl-8.23.0.tar.xz /src/curl.tar.xz
WORKDIR /src
RUN tar -xJf curl.tar.xz --strip-components=1 \
    && ./configure --prefix=/usr/local --without-openssl --with-gnutls --with-ngtcp2 --with-nghttp2 --with-nghttp3 \
        --without-libpsl --disable-static --disable-manual --disable-ldap \
    && make -j"$(nproc)" \
    && make install-strip DESTDIR=/out

FROM alpine:3.24@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6
RUN apk add --no-cache ca-certificates gnutls nghttp2-libs nghttp3 ngtcp2 ngtcp2-gnutls zlib zstd-libs brotli-libs
COPY --from=build /out/usr/local /usr/local
USER 10001:10001
HEALTHCHECK NONE
ENTRYPOINT ["curl"]
