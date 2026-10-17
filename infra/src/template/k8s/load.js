import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

const reads = new Counter('reads');
const writes = new Counter('writes');

const host = __ENV.LOAD_HOST;
const rate = Number(__ENV.LOAD_RATE);
const stage = __ENV.LOAD_DURATION;
const ramp = __ENV.LOAD_RAMP;
const ratio = Number(__ENV.LOAD_WRITE_RATIO);
const tokens = (__ENV.LOAD_TOKENS || '').split(',').filter(Boolean);

export const options = {
    insecureSkipTLSVerify: true,
    discardResponseBodies: true,
    scenarios: {
        traffic: {
            executor: 'ramping-arrival-rate',
            startRate: Math.ceil(rate / 10),
            timeUnit: '1s',
            preAllocatedVUs: Number(__ENV.LOAD_VUS),
            maxVUs: Number(__ENV.LOAD_VUS) * 4,
            stages: [
                { duration: ramp, target: rate },
                { duration: stage, target: rate },
            ],
        },
    },
    thresholds: {
        http_req_failed: ['rate<0.01'],
        http_req_duration: ['p(95)<1000'],
    },
};

export default function () {

    if (tokens.length && Math.random() < ratio) {

        const token = tokens[Math.floor(Math.random() * tokens.length)];
        const res = http.get(`${host}/v1/hello?name=load-${__VU}-${__ITER}`, {
            headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        });

        writes.add(1);
        check(res, { 'write ok': (r) => r.status === 200 });

        return;

    }

    const res = http.get(`${host}/v1/hello`);

    reads.add(1);
    check(res, { 'read ok': (r) => r.status === 200 });

}
