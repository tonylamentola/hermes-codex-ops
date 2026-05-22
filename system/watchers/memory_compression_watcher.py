from __future__ import annotations

import asyncio

from system.services.memory_compressor import MemoryCompressor


async def run() -> None:
    await MemoryCompressor.create().write_context_pack()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
