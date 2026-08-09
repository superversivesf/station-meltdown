import { test, expect, type Page } from '@playwright/test';
import {
  waitForBackend,
  createClient,
  setupGame,
  playSurvivalRound,
  playFinaleRound,
  WsClient,
  type ClientState,
} from './helpers';

let roomCounter = 0;

function uniqueRoom(): string {
  roomCounter++;
  // Generate a unique 4-char code from counter and pid
  const val = (roomCounter * 1000 + (process.pid % 1000)) % 1679616; // base-36 max for 4 chars
  return val.toString(36).toUpperCase().padStart(4, '0');
}

test.beforeAll(async () => {
  await waitForBackend();
});

// Helper: open a browser tab and join a game
async function joinViaUI(page: Page, roomCode: string, name: string) {
  await page.goto('/');
  await page.fill('input[placeholder="ABCD"]', roomCode);
  await page.fill('input[placeholder="Captain Riya"]', name);
  await page.click('button:has-text("Join Game")');
  // Wait for lobby URL
  await page.waitForURL('**/lobby', { timeout: 10000 });
  // Wait for player name to appear in the list (state broadcast received)
  await expect(page.locator(`text=${name}`)).toBeVisible({ timeout: 15000 });
}

// Helper: wait for the play screen
async function waitForPlayScreen(page: Page) {
  await page.waitForURL('**/play', { timeout: 15000 });
  await expect(page.locator('h1:has-text("Round")')).toBeVisible({ timeout: 5000 });
}

// Helper: wait for the finale screen
async function waitForFinaleScreen(page: Page) {
  await page.waitForURL('**/finale', { timeout: 15000 });
  await expect(page.locator('h1:has-text("ESCAPE")')).toBeVisible({ timeout: 5000 });
}

// Helper: wait for the results screen
async function waitForResultsScreen(page: Page) {
  await page.waitForURL('**/results', { timeout: 15000 });
}

// Helper: click a button by text
async function clickButton(page: Page, text: string) {
  await page.click(`button:has-text("${text}")`);
}

test.describe('Station Meltdown — Full Journey Suite', () => {

  test('happy path: 4 players join via UI and win the game', async ({ browser }) => {
    const names = ['Alice', 'Bob', 'Carol', 'Dave'];
    const room = uniqueRoom();
    const pages: Page[] = [];

    // Open 4 browser contexts and join via the UI (all into the SAME room)
    for (let i = 0; i < 4; i++) {
      const context = await browser.newContext();
      const page = await context.newPage();
      pages.push(page);
      await joinViaUI(page, room, names[i]);
    }

    // Verify all 4 players are in the lobby
    await expect(pages[0].locator('text=Crew (4/15)')).toBeVisible({ timeout: 5000 });

    // Host (Alice's page) starts the game
    await pages[0].click('button:has-text("Start Game")');

    // All pages should navigate to /play
    await Promise.all(pages.map((p) => waitForPlayScreen(p)));

    // Play 10 survival rounds — click FIX/BOLSTER buttons through the UI
    for (let round = 0; round < 10; round++) {
      // Each page should have crisis FIX buttons and bolster buttons
      // Strategy: click FIX buttons first, then BOLSTER for remaining players
      for (const page of pages) {
        // Try to click a FIX button (if available)
        const fixButtons = await page.locator('button:has-text("FIX")').count();
        if (fixButtons > 0) {
          await page.click('button:has-text("FIX") >> nth=0');
          // Wait a moment, then confirm
          const confirmBtn = page.locator('button:has-text("Confirm FIX")');
          if (await confirmBtn.count() > 0) {
            await confirmBtn.click();
          }
        } else {
          // No crises to fix — bolster shields
          const bolsterBtns = page.locator('button:has-text("Shields")');
          if (await bolsterBtns.count() > 0) {
            await bolsterBtns.click();
            const confirmBtn = page.locator('button:has-text("Confirm BOLSTER")');
            if (await confirmBtn.count() > 0) {
              await confirmBtn.click();
            }
          }
        }
      }

      // Wait for round to advance (auto-resolve after 2 sec with ACTION_PHASE_SECONDS=2)
      // Or wait for the round number to change
      if (round < 9) {
        await expect(pages[0].locator('h1')).toContainText(`Round ${round + 2}`, { timeout: 15000 });
      } else {
        // After round 10, transition to finale
        await Promise.all(pages.map((p) => waitForFinaleScreen(p)));
      }
    }

    // All pages should be on the finale screen
    await Promise.all(pages.map((p) => waitForFinaleScreen(p)));

    // Play 3 finale rounds — all click RUN
    for (let round = 0; round < 3; round++) {
      for (const page of pages) {
        const runBtn = page.locator('button:has-text("RUN")');
        if (await runBtn.count() > 0) {
          await runBtn.click();
          const confirmBtn = page.locator('button:has-text("Confirm RUN")');
          if (await confirmBtn.count() > 0) {
            await confirmBtn.click();
          }
        }
      }
      // Wait for round advance or results
      if (round < 2) {
        // Wait for next finale round
      } else {
        // Wait for results
        await Promise.all(pages.map((p) => waitForResultsScreen(p)));
      }
    }

    // All pages should be on results
    await Promise.all(pages.map((p) => waitForResultsScreen(p)));

    // Verify victory
    await expect(pages[0].locator('h1:has-text("STATION SAVED")')).toBeVisible({ timeout: 5000 });

    // Cleanup
    for (const page of pages) await page.close();
  });

  test('loss path: reactor meltdown ends the game', async ({ browser }) => {
    const names = ['P1', 'P2', 'P3', 'P4'];
    const r2 = uniqueRoom();
    const clients = await setupGame(r2, names);

    // Start the game
    clients[0].start();
    await Promise.all(clients.map((c) => c.waitForPhase('survival')));

    // Debug: set reactor to 1 so it melts down next round
    clients[0].debugSetSystem('reactor', 1);

    // Everyone bolsters shields (no one fixes the reactor crisis)
    for (const c of clients) {
      c.action('bolster', { target_system: 'shields' });
    }

    // Wait for results — reactor should hit 0
    await Promise.all(clients.map((c) => c.waitForPhase('results', 15000)));

    // Verify loss
    expect(clients[0].lastState!.victory).toBe(false);
    expect(clients[0].lastState!.phase).toBe('results');

    for (const client of clients) client.close();
  });

  test('partial win: some crew escape, some do not', async ({ browser }) => {
    const names = ['Alpha', 'Bravo', 'Charlie', 'Delta'];
    const r3 = uniqueRoom();
    const clients = await setupGame(r3, names);

    clients[0].start();
    await Promise.all(clients.map((c) => c.waitForPhase('survival')));

    // Play survival rounds optimally to reach finale
    for (let round = 0; round < 10; round++) {
      await playSurvivalRound(clients, 'fix-all');
    }

    await Promise.all(clients.map((c) => c.waitForPhase('finale')));

    // Down one player for the partial win scenario
    clients[0].debugDownPlayer('Delta');

    // All 3 rounds: all standing players RUN (no one holds — collapse won't reach 100% in 3 rounds with +34/round = 102)
    // Actually +34*3=102 >= 100, so collapse WILL end the game unless we hold.
    // Strategy: 2 RUN, 1 HOLD each round. 2 players get +3 over 3 rounds (escape), 1 gets +0 (holds, doesn't escape).
    // Wait — we need 3 survivors and 1 lost (Delta). So all 3 standing need to escape.
    // 3 standing * 3 rounds = 9 RUN actions needed. Collapse: 34*3 - 0 holds = 102 >= 100 → collapse ends game.
    // With 1 HOLD per round: 34*3 - 3*15 = 102 - 45 = 57 < 100 → safe. But that's 3 RUN + 1 HOLD = 4 actions/round, 3 standing only have 3.
    // So 2 RUN + 1 HOLD: 2 players get +3 (escape), 1 player gets +0 (doesn't escape).
    // That's 2 survivors + 1 lost standing + 1 lost downed = 2 survived, 2 lost. Not 3-1.
    // 
    // Better: round 1: all 3 RUN (collapse = 34). Round 2: 2 RUN + 1 HOLD (collapse = 34+34-15 = 53). Round 3: 2 RUN + 1 HOLD (collapse = 53+34-15 = 72).
    // All 3 standing: track after round 1 = 1 each. Round 2: 2 run (+1 = 2), 1 holds (stays 1). Round 3: 2 run (+1 = 3), 1 holds (stays 1).
    // 2 escape (track 3), 1 doesn't (track 1), Delta downed (track 0). 2 survived, 2 lost.
    //
    // For 3 survived, 1 lost: we need all 3 standing to reach track 3.
    // 3 RUN each round = 9 actions, collapse = 102 → need holds.
    // Can't do 3 RUN + HOLD with only 3 standing.
    // Solution: 2 rounds of all-RUN (collapse = 68), then 1 round of 2 RUN + 1 HOLD (collapse = 68+34-15 = 87 < 100).
    // Tracks: round 1: all 3 get +1 (track 1). Round 2: all 3 get +1 (track 2). Round 3: 2 get +1 (track 3), 1 holds (track 2).
    // 2 escape (track 3), 1 doesn't (track 2), Delta downed (track 0). Still 2-2.
    //
    // For 3-1 we need all 3 to reach track 3 in 3 rounds with collapse < 100.
    // 3 RUN * 3 rounds = 9 runs, collapse = 102. Need 1 hold total to get 102-15=87.
    // But 1 hold means 1 player skips 1 run → only gets track 2. 
    // Unless... we hold in round 1 (collapse = 34-15 = 19), then all run rounds 2-3 (collapse = 19+34+34 = 87).
    // Tracks: round 1: 1 holds (0), 2 run (1). Round 2: all 3 run (2,2,1). Round 3: all 3 run (3,3,2).
    // 2 escape, 1 doesn't. Still 2-2.
    //
    // The only way to get 3 survivors with 3 standing in 3 rounds: all run every round.
    // Collapse = 102 → need 1 hold to get to 87. But 1 hold = 1 fewer run.
    // Unless a 4th action source exists... no, only 3 standing.
    //
    // Conclusion: with 3 standing and 1 downed, max survivors = 2 (need 1 hold to prevent collapse).
    // Let's adjust the test to expect 2 survived, 2 lost.

    // Strategy: all 3 standing RUN all 3 rounds, but 1 holds in round 1 to prevent collapse
    // Round 1: 2 RUN + 1 HOLD (collapse = 34-15 = 19)
    // Round 2: 3 RUN (collapse = 19+34 = 53)  
    // Round 3: 3 RUN (collapse = 53+34 = 87 < 100)
    // Tracks: 2 players get 3 (ran all 3), 1 player gets 2 (held round 1, ran 2-3), Delta gets 0
    // 2 survived, 2 lost
    const state = clients[0].lastState!;
    const standing = state.players.filter((p) => !p.is_down);
    const alpha = clients.find((c) => c.playerId === standing[0].id)!;
    const bravo = clients.find((c) => c.playerId === standing[1].id)!;
    const charlie = clients.find((c) => c.playerId === standing[2].id)!;

    // Round 1: 2 run, 1 holds
    alpha.action('run');
    bravo.action('run');
    charlie.action('hold');
    await Promise.all(clients.map((c) => c.waitForState((s) => s.round_number === 2)));

    // Round 2: all 3 run
    alpha.action('run');
    bravo.action('run');
    charlie.action('run');
    await Promise.all(clients.map((c) => c.waitForState((s) => s.round_number === 3)));

    // Round 3: all 3 run
    alpha.action('run');
    bravo.action('run');
    charlie.action('run');

    // Wait for results
    await Promise.all(clients.map((c) => c.waitForPhase('results', 15000)));

    // Verify partial win: 2 survived (alpha + bravo at track 3), 2 lost (charlie at track 2, delta downed)
    expect(clients[0].lastState!.partial).toBe(true);
    expect(clients[0].lastState!.crew_survived.length).toBe(2);
    expect(clients[0].lastState!.crew_lost.length).toBe(2);

    for (const client of clients) client.close();
  });

  test('crisis resolution: FIX with insufficient crew fails', async ({ browser }) => {
    const names = ['A1', 'B1', 'C1', 'D1'];
    const r4 = uniqueRoom();
    const clients = await setupGame(r4, names);

    clients[0].start();
    await Promise.all(clients.map((c) => c.waitForPhase('survival')));

    // Find a crisis that requires >= 2 crew
    const state = clients[0].lastState!;
    const crisis = state.active_crises[0];

    if (crisis && crisis.crew_required >= 2) {
      // Only 1 player FIXes (insufficient)
      const beforeHealth = state.systems[crisis.system];
      clients[0].action('fix', {
        target_system: crisis.system,
        target_crisis_id: crisis.id,
      });
      // Others bolster a different system
      for (let i = 1; i < clients.length; i++) {
        clients[i].action('bolster', { target_system: 'shields' });
      }

      await Promise.all(clients.map((c) => c.waitForState((s) => s.round_number === 2)));

      // The crisis system should have drained (insufficient crew)
      const afterState = clients[0].lastState!;
      const afterHealth = afterState.systems[crisis.system];
      expect(afterHealth).toBeLessThan(beforeHealth);
    }

    for (const client of clients) client.close();
  });

  test('finale mechanics: HOLD reduces collapse bar', async ({ browser }) => {
    const names = ['H1', 'H2', 'H3', 'H4'];
    const r5 = uniqueRoom();
    const clients = await setupGame(r5, names);

    clients[0].start();
    await Promise.all(clients.map((c) => c.waitForPhase('survival')));

    // Play through survival
    for (let round = 0; round < 10; round++) {
      await playSurvivalRound(clients, 'fix-all');
    }

    await Promise.all(clients.map((c) => c.waitForPhase('finale')));

    // Round 1: everyone holds
    const state = clients[0].lastState!;
    const standing = state.players.filter((p) => !p.is_down);
    for (const p of standing) {
      const client = clients.find((c) => c.playerId === p.id);
      client?.action('hold');
    }

    await Promise.all(clients.map((c) => c.waitForState((s) => s.round_number === 2)));

    // Collapse bar should be low (34 - 4*15 = -26, clamped to 0)
    const state2 = clients[0].lastState!;
    expect(state2.collapse_bar).toBe(0);

    // Round 2: no one holds — collapse should increase
    for (const p of standing) {
      const client = clients.find((c) => c.playerId === p.id);
      client?.action('run');
    }

    await Promise.all(clients.map((c) => c.waitForState((s) => s.round_number === 3)));

    // Collapse should be 34 (no holds this round)
    const state3 = clients[0].lastState!;
    expect(state3.collapse_bar).toBeGreaterThan(0);

    for (const client of clients) client.close();
  });

  test('finale mechanics: CARRY advances downed crewmate', async ({ browser }) => {
    const names = ['C1', 'C2', 'C3', 'C4'];
    const r6 = uniqueRoom();
    const clients = await setupGame(r6, names);

    clients[0].start();
    await Promise.all(clients.map((c) => c.waitForPhase('survival')));

    // Play through survival
    for (let round = 0; round < 10; round++) {
      await playSurvivalRound(clients, 'fix-all');
    }

    await Promise.all(clients.map((c) => c.waitForPhase('finale')));

    // Down C4
    clients[0].debugDownPlayer('C4');
    await Promise.all(clients.map((c) => c.waitForState((s) => s.players.some((p) => p.name === 'C4' && p.is_down))));

    // Round 1: 2 players carry C4, others hold
    const state = clients[0].lastState!;
    const downed = state.players.find((p) => p.name === 'C4')!;
    const standing = state.players.filter((p) => !p.is_down);

    const carrier1 = clients.find((c) => c.playerId === standing[0].id)!;
    const carrier2 = clients.find((c) => c.playerId === standing[1].id)!;
    carrier1.action('carry', { target_player_id: downed.id });
    carrier2.action('carry', { target_player_id: downed.id });

    // Remaining players hold
    for (const p of standing.slice(2)) {
      const client = clients.find((c) => c.playerId === p.id);
      client?.action('hold');
    }

    await Promise.all(clients.map((c) => c.waitForState((s) => s.round_number === 2)));

    // C4's escape track should be 1
    const state2 = clients[0].lastState!;
    const c4 = state2.players.find((p) => p.name === 'C4')!;
    expect(c4.escape_track).toBe(1);

    for (const client of clients) client.close();
  });

  test('UI renders: join screen shows correct elements', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('h1:has-text("Station Meltdown")')).toBeVisible();
    await expect(page.locator('input[placeholder="ABCD"]')).toBeVisible();
    await expect(page.locator('input[placeholder="Captain Riya"]')).toBeVisible();
    await expect(page.locator('button:has-text("Join Game")')).toBeVisible();
  });

  test('UI renders: lobby shows player list and host badge', async ({ browser }) => {
    const page = await browser.newPage();
    await joinViaUI(page, uniqueRoom(), 'HostPlayer');

    // Verify host badge
    await expect(page.locator('text=Host')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('text=HostPlayer')).toBeVisible({ timeout: 5000 });

    // Verify "need 4 players" warning
    await expect(page.locator('text=Need at least 4 players')).toBeVisible({ timeout: 5000 });

    await page.close();
  });

  test('UI renders: play screen shows systems and crisis cards', async ({ browser }) => {
    // Use 4 browser players to ensure the game starts cleanly
    const names = ['S1', 'S2', 'S3', 'S4'];
    const room = uniqueRoom();
    const pages: Page[] = [];

    for (let i = 0; i < 4; i++) {
      const context = await browser.newContext();
      const page = await context.newPage();
      pages.push(page);
      await joinViaUI(page, room, names[i]);
    }

    // Host starts
    await pages[0].click('button:has-text("Start Game")');
    await Promise.all(pages.map((p) => waitForPlayScreen(p)));

    // Verify station systems are visible on first player's screen (scoped to
    // the systems grid — a bare `text=Reactor` also matches the crisis card
    // and the bolster button, which fails strict-mode locator resolution).
    const systems = pages[0].locator('section.systems .sys-name');
    await expect(systems).toHaveCount(6, { timeout: 5000 });
    await expect(systems.filter({ hasText: 'Reactor' })).toBeVisible();
    await expect(systems.filter({ hasText: 'Life Support' })).toBeVisible();
    await expect(systems.filter({ hasText: 'Hull' })).toBeVisible();
    await expect(pages[0].locator('section.crises h2:has-text("Active Crises")')).toBeVisible({ timeout: 5000 });

    for (const page of pages) await page.close();
  });

  test('reconnect: disconnected player is downed and revived on rejoin', async () => {
    const names = ['R1', 'R2', 'R3', 'R4'];
    const room = uniqueRoom();
    const clients = await setupGame(room, names);

    clients[0].start();
    await Promise.all(clients.map((c) => c.waitForPhase('survival')));

    // Disconnect player R4
    const r4 = clients[3];
    const r4Id = r4.playerId!;
    r4.close();

    // Wait for the disconnect broadcast — R4 should be downed
    await clients[0].waitForState((s) => s.players.some((p) => p.id === r4Id && p.is_down));

    // Reconnect with the same player_id — must reclaim slot and revive
    const r4Rejoin = new WsClient(room);
    await r4Rejoin.connect();
    r4Rejoin.send({ type: 'join', name: 'R4', player_id: r4Id });
    await r4Rejoin.waitForState((s) => {
      const p = s.players.find((p) => p.id === r4Id);
      return p !== undefined && !p.is_down;
    });

    // Verify no duplicate player was created
    expect(r4Rejoin.lastState!.players.length).toBe(4);
    expect(r4Rejoin.playerId).toBe(r4Id);

    for (const client of clients) client.close();
    r4Rejoin.close();
  });
});