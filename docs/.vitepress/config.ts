import { defineConfig } from "vitepress";

// The docs site is served behind the local Traefik ingress under the /-docs/
// path (see local/docker-compose.yml). `base` must match that prefix so that
// generated asset and navigation URLs resolve under it rather than at the
// site root (which the ingress routes to the frontend).
export default defineConfig({
  base: "/-docs/",
  title: "multiplayer-medico",
  description: "multiplayer-medico documentation",
  themeConfig: {
    nav: [
      { text: "Home", link: "/" },
      {
        text: "User Manual",
        link: "/user/",
        activeMatch: "^/user/",
      },
      {
        text: "Development Guide",
        link: "/dev/",
        activeMatch: "^/dev/",
      },
    ],
    sidebar: {
      "/dev/": [
        {
          text: "Development Guide",
          items: [{ text: "Introduction", link: "/dev/" }],
        },
        {
          text: "Overview",
          items: [
            { text: "Architecture", link: "/dev/architecture" },
            { text: "Development bundle", link: "/dev/bundle" },
          ],
        },
        {
          text: "Deep dives",
          items: [
            { text: "Frontend", link: "/dev/frontend-deepdive" },
            { text: "Backend", link: "/dev/backend-deepdive" },
            { text: "Docs", link: "/dev/docs-deepdive" },
          ],
        },
        {
          text: "Libraries",
          items: [
            { text: "dbi18n", link: "/dev/lib/dbi18n" },
            { text: "eventcore", link: "/dev/lib/eventcore" },
            { text: "tracker", link: "/dev/lib/tracker" },
            { text: "uncouple", link: "/dev/lib/uncouple" },
          ],
        },
      ],
      "/user/": [
        {
          text: "User Manual",
          items: [{ text: "Introduction", link: "/user/" }],
        },
      ],
    },
    outline: "deep",
  },
  vite: {
    server: {
      // Served behind the Traefik ingress under a project host
      // (e.g. <project>.orb.local); allow it through Vite's host check.
      allowedHosts: true,
    },
  },
});
