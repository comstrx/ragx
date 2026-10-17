import { createDevice, type Device, webAdapter } from "@/lib/std/device";

export const device: Device = createDevice(webAdapter());
