
import os

from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "danube-chatbot")


def main():
    if not PINECONE_API_KEY:
        raise ValueError("PINECONE_API_KEY is missing in .env")

    print("Connecting to Pinecone...")

    # Initialize Pinecone client
    pc = Pinecone(api_key=PINECONE_API_KEY)

    # Check whether the index exists
    index_names = pc.list_indexes().names()

    if PINECONE_INDEX_NAME not in index_names:
        raise ValueError(
            f"Index '{PINECONE_INDEX_NAME}' not found. "
            f"Available indexes: {index_names}"
        )

    print("Pinecone authentication successful!")

    # Retrieve index configuration
    index_info = pc.describe_index(PINECONE_INDEX_NAME)

    print("Index name:", index_info.name)
    print("Index host:", index_info.host)
    print("Dimension:", index_info.dimension)
    print("Metric:", index_info.metric)
    print("Status:", index_info.status)

    # Connect to the index
    index = pc.Index(host=index_info.host)

    # Retrieve index statistics
    stats = index.describe_index_stats()

    print("Total vector count:", stats.total_vector_count)

    print("\nPinecone connected successfully!")


if __name__ == "__main__":
    main()
