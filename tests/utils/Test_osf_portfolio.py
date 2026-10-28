
import asyncio

from app.retrieval.osf_portfolio_connector import (
    OSFPortfolioConnector,
)

from app.utils.project_tours import (
    build_project_tour_lookup,
)

from app.utils.google_maps import (
    normalize_map_project_name,
)


async def main():

    connector = OSFPortfolioConnector()

    portfolio = await connector.fetch_portfolio()

    print("\nTotal portfolio records:", len(portfolio))

    lookup = build_project_tour_lookup(portfolio)

    print("Total tour lookup entries:", len(lookup))

    print("\nAvailable project tours:")

    for name, url in lookup.items():
        print(f"{name}: {url}")

    test_projects = [
        "Greenz by Danube",
        "Breez by Danube",
        "Oceanz 2",
    ]

    print("\nTesting project matching:")

    for name in test_projects:

        key = normalize_map_project_name(name)

        video_url = lookup.get(key)

        print("\nProject:", name)
        print("Normalized:", key)
        print("Video URL:", video_url or "Not available")


if __name__ == "__main__":
    asyncio.run(main())
