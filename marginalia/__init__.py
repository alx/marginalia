"""marginalia — seven persona agents that publish Wikipedia ZIM content to a private Misskey.

Modules (spec: marginalia-agents.md):
    fetch_zims  §3   download/verify/rotate the topic archives
    zimstore    §4.1 ZimStore + ZimLibrary over libzim
    extract     §4.2 article HTML -> lead, sections, infobox, images
    images      §4.4 image picker, credit line, optional licence check
    publisher   §4.5 Misskey.py wrapper (notes + drive)
    llm         §5/§6 grounded drafting and replies via OpenAI-compatible API
    agent       §5/§6 tick() posting loop, poll() reply loop
    guards      §5.1 grounding, number, length and safety checks
    skills      §4.7 per-topic helper modules
    run         §9   scheduler entry point
"""
