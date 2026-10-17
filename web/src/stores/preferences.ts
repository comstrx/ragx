import { persistent } from "@/lib/providers/storage";
import { preferences } from "@/lib/spec/config";
import { defineStore } from "@/lib/std/state";

export type Theme = "light" | "dark" | "system";
export type Preferences = { language: string; currency: string; theme: Theme };
export type PreferenceActions = { choose: ( patch: Partial<Preferences> ) => void; };

const allowed = <T extends string>( value: T, choices: readonly string[], fallback: T ): T =>
    (choices.includes(value) ? value : fallback);

export const preferenceStore = defineStore<Preferences, PreferenceActions>({
    name: preferences.keys.theme.replace(/\.theme$/, ".preferences"),
    initial: {
        language: preferences.defaults.language,
        currency: preferences.defaults.currency,
        theme: preferences.defaults.theme as Theme,
    },
    actions: ( set, get ) => ({
        choose: ( patch ) => {

            const { languages, currencies, themes } = preferences.choices;
            const current = get();

            set({
                language: allowed(patch.language ?? current.language, languages, current.language),
                currency: allowed(patch.currency ?? current.currency, currencies, current.currency),
                theme: allowed(patch.theme ?? current.theme, themes, current.theme),
            });

        },
    }),
    persist: { store: persistent, keys: ["language", "currency", "theme"] },
});
