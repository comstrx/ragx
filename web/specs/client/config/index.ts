import { defineConfig } from "@/lib/spec/surface";
import contents from "./contents.ts";
import contracts from "./contracts.ts";
import features from "./features.ts";
import settings from "./settings.ts";
import themes from "./themes.ts";

export default defineConfig({ contents, settings, themes, contracts, features });
