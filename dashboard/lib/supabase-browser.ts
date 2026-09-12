import { createBrowserClient } from "@supabase/ssr";

// Singleton: @supabase/ssr's client does async cookie-read initialization on
// creation, so calling this fresh on every request (as api.ts's authHeaders()
// used to) races that init and can return a null session even when a valid
// one exists. One shared instance avoids that race entirely.
let client: ReturnType<typeof createBrowserClient> | undefined;

export function createSupabaseBrowserClient() {
  if (!client) {
    client = createBrowserClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
    );
  }
  return client;
}
