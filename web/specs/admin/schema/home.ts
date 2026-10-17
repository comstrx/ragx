import { block, feature, read, screen, t } from "@/lib/spec/surface";

export default screen({
    contents: {
        name: "home",
        path: "/",
        title: t("hello.title"),
        description: t("hello.description"),
        icon: "house",
    },
    blocks: [
        block({ width: "narrow", height: "screen", padding: 6, align: "center" }, [
            feature("hello", {
                heading: true,
                options: {
                    fallback: t("hello.fallback"),
                    live: t("hello.live"),
                    saved: t("hello.saved"),
                    offline: t("hello.offline"),
                },
                ports: { greeting: read("hello.read") },
            }),
        ]),
    ],
});
