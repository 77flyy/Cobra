**Jupyter, or OKX Aggregator, are on-chain routers where you can perform swaps by interacting with the programs directly on the blockchain.** This has its cons, such as higher transaction costs due to bigger transaction size, and even if you self-host Jupyter, you still get indexer delays, so in the end you waste precious time to find mint's market and pool anyways (this is called `quoting`).

Cobra fixes this issue by asking all [Supported Markets](/#supported-markets) at the same time whether they support passed mint token address, and the market selection is based on the fastest response, in many cases also checks if any liquidity is available, and if there's a pool but there's no liquidity - the **Cobra may fail, but not the transaction**.

Project is open-source, there should be:

- 0 advertisements
- 0 fees
- 0 hidden costs
- 0 wallet-draining logic
- 0 data collection
- 0 tracking
- 0 third-party services

**If any of these points don't match with what you see, please report it: [flock4hcave](https://t.me/flock4hcave)**