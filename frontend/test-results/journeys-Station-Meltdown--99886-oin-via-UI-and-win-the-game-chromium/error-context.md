# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: journeys.spec.ts >> Station Meltdown — Full Journey Suite >> happy path: 4 players join via UI and win the game
- Location: tests/journeys.spec.ts:62:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('text=Crew (4/15)')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for locator('text=Crew (4/15)')

```

```yaml
- heading "Lobby — Room 0147" [level=1]
- heading "Crew (1/15)" [level=2]
- list:
  - listitem: ▸ Alice Host
- paragraph: Need at least 4 players to start. Currently 1.
- button "Start Game" [disabled]
- paragraph: "Connection: connected"
- text: Station Meltdown
```

# Test source

```ts
  1   | import { test, expect, type Page } from '@playwright/test';
  2   | import {
  3   |   waitForBackend,
  4   |   createClient,
  5   |   setupGame,
  6   |   playSurvivalRound,
  7   |   playFinaleRound,
  8   |   WsClient,
  9   |   type ClientState,
  10  | } from './helpers';
  11  | 
  12  | const ROOM_PREFIX = 'J';
  13  | let roomCounter = 0;
  14  | 
  15  | function uniqueRoom(): string {
  16  |   roomCounter++;
  17  |   // Generate a unique 4-char code from counter and pid
  18  |   const val = (roomCounter * 1000 + (process.pid % 1000)) % 1679616; // base-36 max for 4 chars
  19  |   return val.toString(36).toUpperCase().padStart(4, '0');
  20  | }
  21  | 
  22  | test.beforeAll(async () => {
  23  |   await waitForBackend();
  24  | });
  25  | 
  26  | // Helper: open a browser tab and join a game
  27  | async function joinViaUI(page: Page, roomCode: string, name: string) {
  28  |   await page.goto('/');
  29  |   await page.fill('input[placeholder="ABCD"]', roomCode);
  30  |   await page.fill('input[placeholder="Captain Riya"]', name);
  31  |   await page.click('button:has-text("Join Game")');
  32  |   // Wait for lobby URL
  33  |   await page.waitForURL('**/lobby', { timeout: 10000 });
  34  |   // Wait for player name to appear in the list (state broadcast received)
  35  |   await expect(page.locator(`text=${name}`)).toBeVisible({ timeout: 15000 });
  36  | }
  37  | 
  38  | // Helper: wait for the play screen
  39  | async function waitForPlayScreen(page: Page) {
  40  |   await page.waitForURL('**/play', { timeout: 15000 });
  41  |   await expect(page.locator('h1:has-text("Round")')).toBeVisible({ timeout: 5000 });
  42  | }
  43  | 
  44  | // Helper: wait for the finale screen
  45  | async function waitForFinaleScreen(page: Page) {
  46  |   await page.waitForURL('**/finale', { timeout: 15000 });
  47  |   await expect(page.locator('h1:has-text("ESCAPE")')).toBeVisible({ timeout: 5000 });
  48  | }
  49  | 
  50  | // Helper: wait for the results screen
  51  | async function waitForResultsScreen(page: Page) {
  52  |   await page.waitForURL('**/results', { timeout: 15000 });
  53  | }
  54  | 
  55  | // Helper: click a button by text
  56  | async function clickButton(page: Page, text: string) {
  57  |   await page.click(`button:has-text("${text}")`);
  58  | }
  59  | 
  60  | test.describe('Station Meltdown — Full Journey Suite', () => {
  61  | 
  62  |   test('happy path: 4 players join via UI and win the game', async ({ browser }) => {
  63  |     const names = ['Alice', 'Bob', 'Carol', 'Dave'];
  64  |     const pages: Page[] = [];
  65  | 
  66  |     // Open 4 browser contexts and join via the UI
  67  |     for (let i = 0; i < 4; i++) {
  68  |       const context = await browser.newContext();
  69  |       const page = await context.newPage();
  70  |       pages.push(page);
  71  |       await joinViaUI(page, uniqueRoom(), names[i]);
  72  |     }
  73  | 
  74  |     // Verify all 4 players are in the lobby
> 75  |     await expect(pages[0].locator('text=Crew (4/15)')).toBeVisible({ timeout: 5000 });
      |                                                        ^ Error: expect(locator).toBeVisible() failed
  76  | 
  77  |     // Host (Alice's page) starts the game
  78  |     await pages[0].click('button:has-text("Start Game")');
  79  | 
  80  |     // All pages should navigate to /play
  81  |     await Promise.all(pages.map((p) => waitForPlayScreen(p)));
  82  | 
  83  |     // Play 10 survival rounds — click FIX/BOLSTER buttons through the UI
  84  |     for (let round = 0; round < 10; round++) {
  85  |       // Each page should have crisis FIX buttons and bolster buttons
  86  |       // Strategy: click FIX buttons first, then BOLSTER for remaining players
  87  |       for (const page of pages) {
  88  |         // Try to click a FIX button (if available)
  89  |         const fixButtons = await page.locator('button:has-text("FIX")').count();
  90  |         if (fixButtons > 0) {
  91  |           await page.click('button:has-text("FIX") >> nth=0');
  92  |           // Wait a moment, then confirm
  93  |           const confirmBtn = page.locator('button:has-text("Confirm FIX")');
  94  |           if (await confirmBtn.count() > 0) {
  95  |             await confirmBtn.click();
  96  |           }
  97  |         } else {
  98  |           // No crises to fix — bolster shields
  99  |           const bolsterBtns = page.locator('button:has-text("Shields")');
  100 |           if (await bolsterBtns.count() > 0) {
  101 |             await bolsterBtns.click();
  102 |             const confirmBtn = page.locator('button:has-text("Confirm BOLSTER")');
  103 |             if (await confirmBtn.count() > 0) {
  104 |               await confirmBtn.click();
  105 |             }
  106 |           }
  107 |         }
  108 |       }
  109 | 
  110 |       // Wait for round to advance (auto-resolve after 2 sec with ACTION_PHASE_SECONDS=2)
  111 |       // Or wait for the round number to change
  112 |       if (round < 9) {
  113 |         await expect(pages[0].locator('h1')).toContainText(`Round ${round + 2}`, { timeout: 15000 });
  114 |       } else {
  115 |         // After round 10, transition to finale
  116 |         await Promise.all(pages.map((p) => waitForFinaleScreen(p)));
  117 |       }
  118 |     }
  119 | 
  120 |     // All pages should be on the finale screen
  121 |     await Promise.all(pages.map((p) => waitForFinaleScreen(p)));
  122 | 
  123 |     // Play 3 finale rounds — all click RUN
  124 |     for (let round = 0; round < 3; round++) {
  125 |       for (const page of pages) {
  126 |         const runBtn = page.locator('button:has-text("RUN")');
  127 |         if (await runBtn.count() > 0) {
  128 |           await runBtn.click();
  129 |           const confirmBtn = page.locator('button:has-text("Confirm RUN")');
  130 |           if (await confirmBtn.count() > 0) {
  131 |             await confirmBtn.click();
  132 |           }
  133 |         }
  134 |       }
  135 |       // Wait for round advance or results
  136 |       if (round < 2) {
  137 |         // Wait for next finale round
  138 |       } else {
  139 |         // Wait for results
  140 |         await Promise.all(pages.map((p) => waitForResultsScreen(p)));
  141 |       }
  142 |     }
  143 | 
  144 |     // All pages should be on results
  145 |     await Promise.all(pages.map((p) => waitForResultsScreen(p)));
  146 | 
  147 |     // Verify victory
  148 |     await expect(pages[0].locator('h1:has-text("STATION SAVED")')).toBeVisible({ timeout: 5000 });
  149 | 
  150 |     // Cleanup
  151 |     for (const page of pages) await page.close();
  152 |   });
  153 | 
  154 |   test('loss path: reactor meltdown ends the game', async ({ browser }) => {
  155 |     const names = ['P1', 'P2', 'P3', 'P4'];
  156 |     const r2 = uniqueRoom();
  157 |     const clients = await setupGame(r2, names);
  158 | 
  159 |     // Start the game
  160 |     clients[0].start();
  161 |     await Promise.all(clients.map((c) => c.waitForPhase('survival')));
  162 | 
  163 |     // Debug: set reactor to 1 so it melts down next round
  164 |     clients[0].debugSetSystem('reactor', 1);
  165 | 
  166 |     // Everyone bolsters shields (no one fixes the reactor crisis)
  167 |     for (const c of clients) {
  168 |       c.action('bolster', { target_system: 'shields' });
  169 |     }
  170 | 
  171 |     // Wait for results — reactor should hit 0
  172 |     await Promise.all(clients.map((c) => c.waitForPhase('results', 15000)));
  173 | 
  174 |     // Verify loss
  175 |     expect(clients[0].lastState!.victory).toBe(false);
```