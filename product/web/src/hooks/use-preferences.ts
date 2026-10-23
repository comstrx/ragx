"use client";

import { themeOn } from "engine/screen";
import { bind } from "engine/state";
import { useEffect } from "react";
import { type PreferenceActions, type Preferences, preferenceStore, type Theme } from "@/stores/preferences";

const binding = bind(preferenceStore);

export function usePreferences (): Preferences & PreferenceActions & { ready: boolean } {

    return binding.useSelect(( state ) => state);

}
export function useTheme (): Theme {

    const { theme, ready } = usePreferences();

    useEffect(() => {

        if ( ready ) themeOn(document.documentElement, theme);

    }, [theme, ready]);

    return theme;

}
export const PreferencesProvider = binding.Provider;
