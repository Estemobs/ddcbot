"""Helpers HTTP async base sur aiohttp (evite de bloquer la boucle d'evenements)."""

import aiohttp


async def get_json(url: str, timeout: float = 20.0):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            response.raise_for_status()
            return await response.json(content_type=None)


async def get_bytes(url: str, timeout: float = 30.0):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            response.raise_for_status()
            return await response.read()
