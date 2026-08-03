<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { getWs } from '$lib/stores';

  let { children } = $props();

  const startHandler = () => {
    getWs()?.send({ type: 'start' });
  };

  const sendActionHandler = (e: Event) => {
    const detail = (e as CustomEvent).detail;
    getWs()?.send({
      type: 'action',
      action_type: detail.action_type,
      target_system: detail.target_system,
      target_crisis_id: detail.target_crisis_id,
      target_player_id: detail.target_player_id,
    });
  };

  onMount(() => {
    window.addEventListener('start-game', startHandler);
    window.addEventListener('send-action', sendActionHandler);
  });

  onDestroy(() => {
    window.removeEventListener('start-game', startHandler);
    window.removeEventListener('send-action', sendActionHandler);
    getWs()?.close();
  });
</script>

{@render children()}