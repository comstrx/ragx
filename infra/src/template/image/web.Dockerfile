ARG BUN_IMAGE
ARG NODE_IMAGE
FROM ${BUN_IMAGE} AS bun
FROM ${NODE_IMAGE} AS build
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bun
WORKDIR /app
COPY web/package.json web/bun.lock ./
RUN bun install --frozen-lockfile
COPY web/ ./
ARG BUILD_ENV
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN env ${BUILD_ENV} bun run build
RUN env ${BUILD_ENV} bun -e 'import {stage} from "./tools/serve.ts"; import {readFileSync} from "node:fs"; const m=JSON.parse(readFileSync("node_modules/.cache/spec/production/meta.json","utf8")); if(m.output==="standalone") stage(".next/out","public");'
FROM ${NODE_IMAGE}
RUN apk upgrade --no-cache
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bun
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000 HOME=/tmp
COPY --from=build --chown=10001:10001 /app /app
USER 10001:10001
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 CMD ["bun", "-e", "const s=await Bun.connect({hostname:\"127.0.0.1\",port:3000,socket:{data(){},error(){process.exit(1)}}}); s.end(); process.exit(0)"]
CMD ["bun", "run", "start"]
