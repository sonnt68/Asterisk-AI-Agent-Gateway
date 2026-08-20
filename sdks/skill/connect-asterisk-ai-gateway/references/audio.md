# Audio format, and the rate mistake

The encoding is mono PCM signed 16-bit little-endian on the normal transport.
The **sample rate is not fixed**: the gateway announces it per call in
`call.started`'s `media` block. Read it and use it.

```python
rates: dict[str, int] = {}

async def on_event(event):
    if event["type"] == "call.started":
        rates[event["call_id"]] = event["media"]["sample_rate"]
    elif event["type"] == "call.ended":
        rates.pop(event["call_id"], None)
```

The default is 8000 Hz, because a voice trunk is 8 kHz regardless of what
runs above it. A deployment bridging genuinely wideband endpoints may run
higher, and your code has to keep working when it does.

## Why a wrong rate does not announce itself

Every rate change is a resample, and resampling is where quality quietly
goes. Anti-alias filters in most audio libraries only handle **integer
ratios**. If your model emits 24 kHz and you convert to 16 kHz, the ratio is
1.5× — many libraries silently drop the filter and fall back to linear
interpolation, which aliases. Nothing errors. No log line appears. The call
simply sounds wrong.

24 kHz to 8 kHz is 3×, an integer ratio, so the filter stays engaged.

This is not hypothetical. Measured on a live call path, a 16 kHz wire put 56%
of the speech energy inside the 300–3400 Hz telephony band; the 8 kHz path put
68% there. Listeners described the difference as "boomy and far away" and
could not say why.

Two consequences worth internalising:

- **A wider wire does not widen the call.** The trunk is 8 kHz either way. A
  higher rate between you and the gateway only adds conversions, each of which
  can cost you.
- **When you must resample, prefer an integer ratio** over a nominally higher
  rate. Choosing your model's output format so that the ratio to the call's
  rate is a whole number is worth more than the extra bandwidth.

## Debugging audio quality

Symptoms like "muffled", "boomy", "distant", or "robotic" with no errors
anywhere are almost always a rate or resampling problem, not a network one.
Work through it in this order:

1. Log the rate in `call.started` and the rate your code actually sends.
   Assume nothing; the gap between them is usually the answer.
2. Check the ratio between your model's native rate and the call's rate. If it
   is not a whole number, find out what your resampler does about it.
3. Capture the audio you are sending, before it reaches the SDK. A recording
   made on the phone contains both speakers and cannot tell you anything about
   your own output.
