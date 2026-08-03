<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { getWs } from '$lib/stores';

  let { children } = $props();

  const startHandler = () => {
    getWs()?.send({ type: 'start' });
  };

  onMount(() => {
    window.addEventListener('start-game', startHandler);
  });

  onDestroy(() => {
    window.removeEventListener('start-game', startHandler);
    getWs()?.close();
  });
</script>

{@render children()}