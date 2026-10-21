# Rebuild one module against the exact pilot image; do not upgrade the PBX core.
ARG FREEPBX_BASE=escomputers/freepbx@sha256:34e65b7a0a02ad9da67315c12bcfd0368a89c3f6d185abf498ae8a48687f0daa
FROM ${FREEPBX_BASE} AS build
USER root
WORKDIR /usr/src/gateway-audiosocket
RUN echo '9624e807a1138cabed14431a326c9870e53fc132738dbbd61314abc027785d94  /usr/src/asterisk.tar.gz' | sha256sum -c - \
    && tar -xzf /usr/src/asterisk.tar.gz
WORKDIR /usr/src/gateway-audiosocket/asterisk-21.10.2
COPY res_audiosocket-21.10.2-header-read.patch /tmp/audiosocket.patch
RUN echo 'a9ff97eca61dad09148ccb67de5584c0c6854d8cc748f916d6585d055f6c62da  res/res_audiosocket.c' | sha256sum -c - \
    && patch --fuzz=0 -p1 < /tmp/audiosocket.patch \
    && ./configure --libdir=/usr/lib64 --with-pjproject-bundled --with-jansson-bundled \
    && make menuselect.makeopts \
    && menuselect/menuselect --disable BUILD_NATIVE --enable format_mp3 \
         --disable-category MENUSELECT_RES --enable res_audiosocket menuselect.makeopts \
    && make res
RUN grep -F '#define AST_BUILDOPT_SUM "da6642af068ee5e6490c5b1d2cc1d238"' include/asterisk/buildopts.h \
    && nm -D /usr/sbin/asterisk | grep -w ast_null_frame \
    && nm -D --undefined-only /usr/lib64/asterisk/modules/res_audiosocket.so | sort > /tmp/original-symbols \
    && nm -D --undefined-only res/res_audiosocket.so | grep -v -w ast_null_frame | sort > /tmp/patched-symbols \
    && diff -u /tmp/original-symbols /tmp/patched-symbols \
    && test "$(readelf -d res/res_audiosocket.so | grep -c NEEDED)" = 1 \
    && readelf -d res/res_audiosocket.so | grep NEEDED | grep -F '[libc.so.6]'

FROM ${FREEPBX_BASE}
COPY --from=build --chown=asterisk:asterisk \
    /usr/src/gateway-audiosocket/asterisk-21.10.2/res/res_audiosocket.so \
    /usr/lib64/asterisk/modules/res_audiosocket.so
LABEL org.asterisk-ai-gateway.audiosocket-patch="21.10.2-header-read"
