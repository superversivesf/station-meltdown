# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: journeys.spec.ts >> Station Meltdown — Full Journey Suite >> UI renders: play screen shows systems and crisis cards
- Location: tests/journeys.spec.ts:420:3

# Error details

```
TimeoutError: page.click: Timeout 10000ms exceeded.
Call log:
  - waiting for locator('button:has-text("Start Game")')
    - locator resolved to <button disabled class="svelte-1xhi2iz">Start Game</button>
  - attempting click action
    2 × waiting for element to be visible, enabled and stable
      - element is not enabled
    - retrying click action
    - waiting 20ms
    2 × waiting for element to be visible, enabled and stable
      - element is not enabled
    - retrying click action
      - waiting 100ms
    19 × waiting for element to be visible, enabled and stable
       - element is not enabled
     - retrying click action
       - waiting 500ms

```

# Page snapshot

```yaml
- generic [ref=e2]:
  - generic [ref=e3]:
    - heading "Lobby — Room 05VO" [level=1] [ref=e4]
    - generic [ref=e5]:
      - heading "Crew (1/15)" [level=2] [ref=e6]
      - list [ref=e7]:
        - listitem [ref=e8]:
          - text: ▸ S1
          - generic [ref=e9]: Host
    - paragraph [ref=e10]: Need at least 4 players to start. Currently 1.
    - button "Start Game" [disabled] [ref=e11]
    - paragraph [ref=e12]: "Connection: connected"
  - generic [ref=e13]: Station Meltdown
```

# Test source

```ts
  333 |     // Collapse bar should be low (34 - 4*15 = -26, clamped to 0)
  334 |     const state2 = clients[0].lastState!;
  335 |     expect(state2.collapse_bar).toBe(0);
  336 | 
  337 |     // Round 2: no one holds — collapse should increase
  338 |     for (const p of standing) {
  339 |       const client = clients.find((c) => c.playerId === p.id);
  340 |       client?.action('run');
  341 |     }
  342 | 
  343 |     await Promise.all(clients.map((c) => c.waitForState((s) => s.round_number === 3)));
  344 | 
  345 |     // Collapse should be 34 (no holds this round)
  346 |     const state3 = clients[0].lastState!;
  347 |     expect(state3.collapse_bar).toBeGreaterThan(0);
  348 | 
  349 |     for (const client of clients) client.close();
  350 |   });
  351 | 
  352 |   test('finale mechanics: CARRY advances downed crewmate', async ({ browser }) => {
  353 |     const names = ['C1', 'C2', 'C3', 'C4'];
  354 |     const r6 = uniqueRoom();
  355 |     const clients = await setupGame(r6, names);
  356 | 
  357 |     clients[0].start();
  358 |     await Promise.all(clients.map((c) => c.waitForPhase('survival')));
  359 | 
  360 |     // Play through survival
  361 |     for (let round = 0; round < 10; round++) {
  362 |       await playSurvivalRound(clients, 'fix-all');
  363 |     }
  364 | 
  365 |     await Promise.all(clients.map((c) => c.waitForPhase('finale')));
  366 | 
  367 |     // Down C4
  368 |     clients[0].debugDownPlayer('C4');
  369 |     await Promise.all(clients.map((c) => c.waitForState((s) => s.players.some((p) => p.name === 'C4' && p.is_down))));
  370 | 
  371 |     // Round 1: 2 players carry C4, others hold
  372 |     const state = clients[0].lastState!;
  373 |     const downed = state.players.find((p) => p.name === 'C4')!;
  374 |     const standing = state.players.filter((p) => !p.is_down);
  375 | 
  376 |     const carrier1 = clients.find((c) => c.playerId === standing[0].id)!;
  377 |     const carrier2 = clients.find((c) => c.playerId === standing[1].id)!;
  378 |     carrier1.action('carry', { target_player_id: downed.id });
  379 |     carrier2.action('carry', { target_player_id: downed.id });
  380 | 
  381 |     // Remaining players hold
  382 |     for (const p of standing.slice(2)) {
  383 |       const client = clients.find((c) => c.playerId === p.id);
  384 |       client?.action('hold');
  385 |     }
  386 | 
  387 |     await Promise.all(clients.map((c) => c.waitForState((s) => s.round_number === 2)));
  388 | 
  389 |     // C4's escape track should be 1
  390 |     const state2 = clients[0].lastState!;
  391 |     const c4 = state2.players.find((p) => p.name === 'C4')!;
  392 |     expect(c4.escape_track).toBe(1);
  393 | 
  394 |     for (const client of clients) client.close();
  395 |   });
  396 | 
  397 |   test('UI renders: join screen shows correct elements', async ({ page }) => {
  398 |     await page.goto('/');
  399 | 
  400 |     await expect(page.locator('h1:has-text("Station Meltdown")')).toBeVisible();
  401 |     await expect(page.locator('input[placeholder="ABCD"]')).toBeVisible();
  402 |     await expect(page.locator('input[placeholder="Captain Riya"]')).toBeVisible();
  403 |     await expect(page.locator('button:has-text("Join Game")')).toBeVisible();
  404 |   });
  405 | 
  406 |   test('UI renders: lobby shows player list and host badge', async ({ browser }) => {
  407 |     const page = await browser.newPage();
  408 |     await joinViaUI(page, uniqueRoom(), 'HostPlayer');
  409 | 
  410 |     // Verify host badge
  411 |     await expect(page.locator('text=Host')).toBeVisible({ timeout: 5000 });
  412 |     await expect(page.locator('text=HostPlayer')).toBeVisible({ timeout: 5000 });
  413 | 
  414 |     // Verify "need 4 players" warning
  415 |     await expect(page.locator('text=Need at least 4 players')).toBeVisible({ timeout: 5000 });
  416 | 
  417 |     await page.close();
  418 |   });
  419 | 
  420 |   test('UI renders: play screen shows systems and crisis cards', async ({ browser }) => {
  421 |     // Use 4 browser players to ensure the game starts cleanly
  422 |     const names = ['S1', 'S2', 'S3', 'S4'];
  423 |     const pages: Page[] = [];
  424 | 
  425 |     for (let i = 0; i < 4; i++) {
  426 |       const context = await browser.newContext();
  427 |       const page = await context.newPage();
  428 |       pages.push(page);
  429 |       await joinViaUI(page, uniqueRoom(), names[i]);
  430 |     }
  431 | 
  432 |     // Host starts
> 433 |     await pages[0].click('button:has-text("Start Game")');
      |                    ^ TimeoutError: page.click: Timeout 10000ms exceeded.
  434 |     await Promise.all(pages.map((p) => waitForPlayScreen(p)));
  435 | 
  436 |     // Verify station systems are visible on first player's screen
  437 |     await expect(pages[0].locator('text=Reactor')).toBeVisible({ timeout: 5000 });
  438 |     await expect(pages[0].locator('text=Life Support')).toBeVisible({ timeout: 5000 });
  439 |     await expect(pages[0].locator('text=Hull')).toBeVisible({ timeout: 5000 });
  440 |     await expect(page.locator('h2:has-text("Active Crises")')).toBeVisible({ timeout: 5000 });
  441 | 
  442 |     for (const page of pages) await page.close();
  443 |   });
  444 | });
```