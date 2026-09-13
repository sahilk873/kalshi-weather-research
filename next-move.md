We have enough historical Kalshi/weather data to do a strong **predictive-alpha and market-mispricing backtest**, but not enough to claim a fully realistic historical execution/P&L backtest yet.

A few important distinctions/corrections:

* Historical Kalshi trades are useful and their exchange timestamps are meaningful: they prove that someone traded at price P at time T. They do **not** prove that we could have filled at that price, in that size, with our queue position.
* Historical candles are useful as price proxies, but they are aggregates and cannot reconstruct the exact bid/ask/order-book state at our decision time.
* The lack of a historical full order-book stream means we cannot rigorously simulate spread crossing, depth, queue position, cancellations, partial fills, slippage, adverse selection, etc.
* Settlement observations received after the event are still perfectly valid **labels/targets**. A label is allowed to arrive after prediction time. The leakage issue only arises if we use information as a predictor that was not actually available at the model decision timestamp.
* For any historical predictor reconstructed after the fact, the key question is not just whether we have the value now, but whether we can establish or conservatively approximate when that information would have become available historically.
* Any forecast, observation, derived signal, third-party feed, station reading, model output, market feature, or other feature used in the backtest should be governed by the same point-in-time rule.
* Do not use retrospective/revised/reanalyzed information as if it had been available operationally at the historical decision time unless we can justify that assumption.
* Kalshi daily temperature settlement transitioned from NWS to The Weather Company effective Aug. 14, 2026. Do not describe the source change as TWC -> Synoptic. Any source-era analysis should reflect the actual settlement regime.

The historical market data we currently have is still valuable:

* ~75,040 city-market rows across NYC/LA/Austin/Phoenix/Las Vegas
* ~612,998 historical public trades in the broader archive
* ~32,076 aggregate candles
* 15,883 NYC hourly markets with exact settlement/label joins
* much deeper NYC coverage than LA/Austin
* plus a broader set of weather, forecast, observation, station, model, market, and derived-feature data that should all be incorporated where point-in-time validity can be established

What I want to do next:

1. **Build a general point-in-time feature store.**

   The core key should be something like:

   `(city, contract, target_date/target_hour, decision_timestamp)`

   Every feature should carry enough metadata to establish historical availability, for example:

   * source/provider
   * feature name
   * source timestamp
   * observation/init/issue time where applicable
   * valid time where applicable
   * revision/version where applicable
   * known or estimated `available_at`
   * retrieval time if relevant
   * value
   * decision timestamp
   * provenance/raw-source reference

   Enforce the central rule:

   `available_at <= decision_time`

   This should apply universally across all predictors.

2. **Reconstruct historical feature vintages wherever possible.**

   For every decision timestamp, rebuild the information set that a trader could reasonably have possessed at that moment.

   This can include:

   * operational forecast/model runs
   * station and observational feeds
   * third-party weather feeds
   * derived meteorological features
   * ensemble/model outputs
   * historical market information
   * cross-source differences
   * temporal features
   * alternative/external datasets
   * any other predictors we decide are useful

   Where exact publication timestamps exist, use them.

   Where they do not, use conservative availability assumptions and document them.

   Do not simply take the latest historical value we can download today.

3. **Use historical observations/features where appropriate, but explicitly model latency and revision risk.**

   For sources where historical data was retrieved after the fact, run several plausible availability assumptions rather than silently assuming zero latency.

   For example:

   * optimistic
   * realistic/base
   * conservative
   * highly conservative

   Where independent contemporaneous data exists, use it to validate whether the reconstructed historical feed appears consistent with what likely existed in real time.

   Quantify:

   * value agreement
   * timestamp differences
   * revision/correction frequency
   * missingness
   * provider disagreement
   * latency distribution

4. **Separate the research into three layers.**

   **A. Predictive/weather alpha**

   Does the feature set/model accurately predict the final settlement variable or temperature distribution?

   Evaluate with:

   * log loss
   * Brier score
   * CRPS
   * calibration
   * MAE/RMSE
   * bucket probability calibration
   * directional/bucket accuracy where relevant

   **B. Market informational alpha**

   Does our model systematically identify cases where the market-implied probability appears wrong?

   Conceptually:

   `edge = model_probability - observed_market_probability`

   Then test whether outcomes conditional on predicted edge behave the way the model says they should.

   **C. Executable trading alpha**

   We cannot make a fully defensible historical claim yet because we lack continuous historical order-book replay.

   Treat any historical execution/P&L result here as hypothetical or stress-tested rather than exact.

5. **Build a conservative historical pseudo-execution framework using the market data we do have.**

   Use trades, candles, and any other historical price evidence to construct deliberately conservative execution proxies.

   Examples:

   * require an actual trade after signal generation
   * restrict execution to a short post-signal window
   * assume a worse price than the observed trade
   * apply fees
   * penalize for latency
   * limit assumed size
   * reject trades where market evidence is too sparse

   Run multiple assumptions:

   * +1¢
   * +2¢
   * +3¢
   * +5¢ price deterioration

   and:

   * 0 sec
   * 10 sec
   * 30 sec
   * 1 min
   * 5 min execution latency

   The goal is not to claim exact fills. The goal is to determine whether the informational alpha remains economically meaningful under increasingly unfavorable execution assumptions.

6. **Start full prospective Kalshi WebSocket collection immediately — starting today.**

   This should be a top-priority engineering task.

   Connect to the Kalshi WebSocket feed and continuously persist the raw event stream for every relevant weather market we may trade or study.

   At minimum capture:

   * market ticker
   * event ticker
   * exchange/server timestamp if supplied
   * local receive timestamp
   * WebSocket sequence/order identifier if supplied
   * message type
   * order-book snapshot events
   * order-book delta events
   * trades
   * price
   * size
   * side
   * bid levels
   * ask levels
   * displayed size at each available depth level
   * market status changes
   * open/close/expiration events
   * any relevant market metadata changes

   Do **not** only persist a derived top-of-book table.

   Save the **raw WebSocket messages** as well so that we can rebuild the book later if our parser or research methodology changes.

   Prefer an append-only raw event store such as:

   `received_at | exchange_timestamp | ticker | channel | sequence_id | raw_json`

   Then create normalized downstream tables from that raw stream.

7. **Maintain reconstructable order-book state from the WebSocket stream.**

   For every tracked market, we should be able to reconstruct:

   * best bid
   * best ask
   * spread
   * bid depth
   * ask depth
   * multiple depth levels
   * imbalance
   * recent trade flow
   * cancellations/book changes
   * time since last trade
   * time since last quote change

   at any historical timestamp after collection begins.

   The raw WebSocket stream should be considered the source of truth.

   Periodically persist full book snapshots/checkpoints as well so we do not need to replay the entire history from inception every time.

   Something like:

   `raw WS events -> deterministic book builder -> periodic L2 snapshots`

8. **Record both exchange time and our own receive time.**

   This is very important.

   For every WebSocket/API/external-data message, store:

   * source event timestamp
   * local wall-clock receive timestamp
   * processing timestamp where useful

   We care about the information available to **our system**, not merely when the exchange says an event occurred.

   This lets us estimate actual latency:

   `receive_latency = local_received_at - exchange_timestamp`

   and prevents us from accidentally backtesting on information that our bot would not yet have seen.

9. **Continuously collect relevant markets, not only markets where the current strategy decides to trade.**

   We do not want future selection bias.

   Subscribe to the broad relevant weather-market universe and retain data even when:

   * model edge is zero
   * we do not place an order
   * liquidity is bad
   * the contract looks uninteresting
   * the model fails to generate a prediction

   Otherwise we risk creating a dataset containing only the markets our current strategy happened to care about.

10. **Snapshot REST state alongside WebSocket state.**

WebSocket should be the primary continuous stream, but periodically query the relevant REST endpoints too.

Use those snapshots to:

* initialize books
* detect dropped WebSocket messages
* reconcile sequence gaps
* verify state
* recover after disconnects

Store the REST response with its own retrieval timestamp and raw response.

If a WebSocket connection drops or sequence continuity breaks:

* mark the affected interval
* re-request current state
* rebuild from a fresh snapshot
* do not silently treat the gap as complete historical data

11. **Collect all external predictor data prospectively at the same time.**

The Kalshi stream alone is not enough.

Starting today, archive every external input actually used or potentially useful to the model, with the raw response and retrieval timestamp.

This should include the broader universe of:

* weather observations
* model forecasts
* ensembles
* third-party provider data
* alternative weather feeds
* station feeds
* model-derived features
* relevant metadata
* any additional external signal we introduce later

Use a source-agnostic ingestion pattern:

`provider`
`retrieved_at`
`source_event_time`
`issue_time`
`valid_time`
`version`
`request_parameters`
`raw_response`
`parsed_features`

The objective is that months from now we know **exactly what our strategy could have known at every decision timestamp**.

12. **Record every model prediction prospectively.**

Never regenerate a historical prediction later and pretend it was the live signal.

For every prediction made live, store:

* prediction timestamp
* model version/hash
* feature-set version
* exact feature values
* model probability/distribution
* fair value
* current Kalshi bid/ask/book state
* calculated edge
* strategy threshold
* resulting decision

Example:

`decision_time`
`model_version`
`p_yes`
`market_bid`
`market_ask`
`edge_vs_bid`
`edge_vs_ask`
`desired_side`
`desired_price`
`desired_size`

This gives us a true prospective signal ledger.

13. **Record hypothetical orders even when we are paper trading.**

The system should produce the exact order it **would** have sent:

* side
* price
* size
* order type
* signal timestamp
* submission timestamp
* cancellation logic
* replacement logic

Then replay subsequent WebSocket/order-book events to determine whether the hypothetical order would plausibly have filled.

Maintain separate concepts for:

* model signal
* desired order
* simulated submitted order
* simulated fill
* actual live order, if/when we begin trading

Do not collapse these into one field.

14. **Build a prospective paper-trading execution engine.**

Once live WebSocket data is flowing, simulate the actual strategy in real time.

Track:

* crossing versus passive orders
* available depth
* partial fills
* remaining quantity
* cancellations
* repricing
* latency
* fees
* markouts after fill
* settlement P&L

Passive fill modeling should be conservative because we do not know exact queue position.

Ideally retain multiple fill assumptions:

* pessimistic
* base
* optimistic

Then we can tell whether apparent profitability depends on aggressive fill assumptions.

15. **Log data gaps and system health.**

The future dataset is only trustworthy if we know where it is incomplete.

Persist:

* WebSocket connects/disconnects
* sequence gaps
* API failures
* rate-limit events
* parser failures
* missing provider updates
* process restarts
* clock synchronization problems
* stale-feed warnings

Each interval should eventually be classifiable as:

* complete
* partially complete
* unreliable

Exclude unreliable intervals from rigorous execution research instead of silently filling them.

16. **Make the entire backtest architecture source-agnostic.**

Do not hard-code the framework around a small set of named data providers.

The system should support arbitrary features as long as they satisfy the PIT contract.

Something like:

`feature_name`
`source`
`source_event_time`
`available_at`
`decision_time`
`value`
`version/revision`
`provenance`

Any feature can enter the model if:

`available_at <= decision_time`

17. **Use proper temporal validation.**

Do not use ordinary random K-fold CV.

Preserve temporal ordering and avoid leakage from overlapping/highly correlated contracts.

Use some combination of:

* expanding-window validation
* rolling-window validation
* walk-forward testing
* purging/embargo where needed
* untouched final holdout periods

Hyperparameter tuning, feature selection, probability calibration, model selection, and trading thresholds all need to happen strictly inside the appropriate training/validation window.

18. **Run sensitivity analysis aggressively.**

Test across:

* feature availability assumptions
* provider latency assumptions
* publication delays
* observation delays
* missing data
* revised data
* provider disagreement
* execution latency
* worse entry prices
* fees
* size assumptions
* city-by-city splits
* season/year splits
* source-regime splits
* liquidity regimes
* different decision times
* different model/feature subsets
* different fill assumptions

If an apparent edge only exists under one optimistic assumption, it should not be considered robust.

19. **Be careful with claims.**

Until we have a sufficiently large prospective dataset with complete WebSocket/order-book history, frame historical results as:

* predictive alpha
* market mispricing / informational alpha
* robustness under hypothetical execution stress tests

Do not claim:

* exact historical fills
* exact historical P&L
* exact historical queue position
* fully executable historical Sharpe
* precise historical capacity

Going forward, the prospective dataset should eventually allow us to make much stronger execution-level claims.

The most important architectural change is: do not organize the research as:

`date -> features -> result`

Organize it as:

`(city, contract, decision_timestamp)`

↓

`complete information set demonstrably available to us at that instant`

↓

`model probability/distribution`

↓

`actual Kalshi market state at that instant`

↓

`strategy decision / hypothetical order`

↓

`subsequent order-book/trade path`

↓

`simulated or actual fill`

↓

`eventual settlement`

This lets us independently evaluate:

1. forecast quality,
2. informational edge versus the market,
3. robustness to execution assumptions,
4. realistic paper-trading performance,
5. and eventually true executable alpha.

**Immediate priorities should be:**

1. Start the Kalshi WebSocket/raw-order-book collector **today**.
2. Start timestamped archival of all external predictor feeds **today**.
3. Start recording every live model prediction and hypothetical order **today**.
4. Build the PIT feature-store architecture.
5. Reconstruct historical feature vintages across all available sources.
6. Build the historical informational-alpha backtest.
7. Build conservative pseudo-execution stress tests.
8. Build the prospective paper-trading/replay engine on top of the live WebSocket archive.

The reason to prioritize live collection immediately is simple: **every day we are not recording the full market and information state is historical data we can never perfectly recreate later.**

