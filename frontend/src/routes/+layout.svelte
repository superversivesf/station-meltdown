<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { getWs, gameState } from '$lib/stores';

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

  // Auto-route based on phase. Fires on the FIRST non-null phase too (not
  // just on phase changes) because lastPhase starts null — so a reload
  // mid-game on /play while the game is in finale/results redirects to the
  // right screen on the first state broadcast.
  let lastPhase: string | null = $state(null);
  $effect(() => {
    const phase = $gameState?.phase ?? null;
    if (phase && phase !== lastPhase) {
      lastPhase = phase;
      if (phase === 'survival') goto('/play');
      else if (phase === 'finale') goto('/finale');
      else if (phase === 'results') goto('/results');
    }
  });
</script>

{@render children()}