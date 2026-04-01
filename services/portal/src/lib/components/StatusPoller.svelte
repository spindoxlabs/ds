<script lang="ts">
  import { onMount, onDestroy } from 'svelte';

  let {
    pollFn,
    intervalMs = 3000,
    stopWhen,
    children,
  }: {
    pollFn: () => Promise<unknown>;
    intervalMs?: number;
    stopWhen?: (data: unknown) => boolean;
    children: import('svelte').Snippet<[{ data: unknown; loading: boolean; error: string | null }]>;
  } = $props();

  let data = $state<unknown>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let timer: ReturnType<typeof setInterval>;

  async function tick() {
    try {
      data = await pollFn();
      error = null;
      if (stopWhen?.(data)) clearInterval(timer);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Unknown error';
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    tick();
    timer = setInterval(tick, intervalMs);
  });

  onDestroy(() => clearInterval(timer));
</script>

{@render children({ data, loading, error })}
