"use client";

import { useEffect } from "react";
import { preferences } from "@/lib/spec/config";
import { bind } from "@/lib/std/state";
import { type PreferenceActions, type Preferences, preferenceStore, type Theme } from "@/stores/preferences";

const binding = bind(preferenceStore);

function apply ( theme: Theme ): void {

    const root = document.documentElement;

    if ( theme === "system" ) delete root.dataset.theme;
    else root.dataset.theme = theme;

    try { localStorage.setItem(preferences.keys.theme, JSON.stringify(theme)); }
    catch { return; }

}
export function usePreferences (): Preferences & PreferenceActions & { ready: boolean } {

    return binding.useSelect(( state ) => state);

}
export function useTheme (): Theme {

    const { theme, ready } = usePreferences();

    useEffect(() => {

        if ( ready ) apply(theme);

    }, [theme, ready]);

    return theme;

}
export const PreferencesProvider = binding.Provider;
