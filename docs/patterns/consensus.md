# consensus

Run parallel LLM samples and aggregate via voting.

::: executionkit.patterns.consensus.consensus

## Example

```python
from executionkit import consensus, Provider

provider = Provider("https://api.openai.com/v1", api_key=KEY, model="gpt-4o-mini")

result = await consensus(
    provider,
    "Classify this email as spam or not-spam: ...",
    num_samples=5,
    strategy="majority",
)

print(result.value)                           # "not-spam"
print(result.metadata["agreement_ratio"])     # 0.8
print(result.metadata["unique_responses"])    # 2
```

## Voting Strategies

| Strategy | Behaviour |
|----------|-----------|
| `"majority"` | Most common response wins. Ties broken by first occurrence. |
| `"unanimous"` | All responses must match; raises `ConsensusFailedError` otherwise. |

## Metadata Keys

| Key | Type | Description |
|-----|------|-------------|
| `agreement_ratio` | `float` | Fraction of samples matching the winner (0.0–1.0) |
| `unique_responses` | `int` | Number of distinct response strings observed |
| `tie_count` | `int` | Number of responses tied for top vote count |
