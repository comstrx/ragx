import build from "@spec/build";
import routing from "@spec/routing";
import settings from "@spec/settings";

export { build, routing };

const selected = process.env.NEXT_PUBLIC_SPEC;

if ( !selected ) throw new Error("The build must select NEXT_PUBLIC_SPEC.");

export const identity = selected;

export const preferences = {
    keys: { language: `${selected}.language`, currency: `${selected}.currency`, theme: `${selected}.theme` },
    choices: { languages: settings.languages, currencies: settings.currencies, themes: settings.themes },
    defaults: { language: settings.language, currency: settings.currency, theme: settings.theme },
};
