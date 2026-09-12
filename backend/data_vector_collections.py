import os
from pathlib import Path
from docling_core.transforms.chunker import HierarchicalChunker
from langchain_qdrant import QdrantVectorStore
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client.http.models import Filter, FieldCondition, MatchAny
from backend.config import settings
from langchain_docling import DoclingLoader
from langchain_docling.loader import ExportType

# 1. RBAC Mapping Required by the FinBot Assignment
# This maps each collection folder to the user roles that are authorized to access it
RBAC_MAPPING = {
    "general": ["employee", "finance", "engineering", "marketing", "c_level"],
    "finance": ["finance", "c_level"],
    "engineering": ["engineering", "c_level"],
    "marketing": ["marketing", "c_level"],
}

def get_role_filter(user_role: str):
    """
    Returns a Qdrant Filter that restricts results to
    what the given role is allowed to see.
    """
    valid_roles = {"employee", "finance", "engineering", "marketing", "c_level"}
    
    if user_role == "c_level":
        return None
        
    elif user_role in valid_roles:
        return Filter(
            must=[
                FieldCondition(
                    key="metadata.access_roles",
                    match=MatchAny(any=[user_role])
                )
            ]
        )
        
    else:
        raise ValueError(f"Unknown role: '{user_role}'. Expected one of {valid_roles}.")

EMBED_MODEL_ID = settings.embed_model_id
embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL_ID)

def load_document(source: str):
    """
    Parse a document using Docling.
    """
    documents = DoclingLoader(
    file_path=source,
    export_type=ExportType.DOC_CHUNKS,
    chunker=HierarchicalChunker(),
    ).load()
            
    return documents

def enrich_langchain_doc(lc_doc: Document, source: str, collection: str, access_roles: list) -> Document:
    """
    Takes a LangChain Document produced by DoclingLoader and injects the FinBot RBAC metadata,
    ensuring compliance with the assignment metadata schema.
    """
    original_meta = lc_doc.metadata

    # Extract info from DoclingLoader's rich metadata
    docling_meta = original_meta.get("dl_meta", {})
    
    # page_content is already correctly populated by DoclingLoader
    page_content = lc_doc.page_content

    # Derive mandatory FinBot metadata fields
    source_filename = Path(source).name
    
    # DoclingLoader puts headings in a list under dl_meta['doc_items'][0]['prov'][0]['headings']
    # But it's easier to just grab the 'heading' key that is sometimes surfaced or fall back.
    # Often DoclingLoader extracts the current heading directly or we can get it from the text if it's a heading chunk.
    section_title = ""
    doc_items = docling_meta.get("doc_items", [])
    if doc_items and "prov" in doc_items[0] and doc_items[0]["prov"]:
        headings_list = doc_items[0]["prov"][0].get("headings", [])
        if headings_list:
            section_title = headings_list[-1]
    
    page_number = original_meta.get("page", 1)
    
    # Determine chunk type. Docling loader might have it in doc_items
    chunk_type = "text"
    doc_items = docling_meta.get("doc_items", [])
    if doc_items:
        content_layer = doc_items[0].get("content_layer", "body")
        if content_layer == "table":
            chunk_type = "table"
        elif content_layer in ["section_header", "page_header"]:
            chunk_type = "heading"
        elif content_layer == "code":
            chunk_type = "code"

            
    parent_chunk_id = ""
    if doc_items and doc_items[0].get("parent"):
        parent_chunk_id = str(doc_items[0].get("parent", {}).get("$ref", ""))

    # Build the required top-level metadata dict
    finbot_metadata = {
        "source_document": source_filename,
        "collection": collection,
        "access_roles": access_roles,
        "section_title": section_title,
        "page_number": page_number,
        "chunk_type": chunk_type,
        "parent_chunk_id": parent_chunk_id,
        "source": source
    }

    # Merge original metadata with FinBot metadata (FinBot takes precedence for core fields)
    merged_metadata = {**original_meta, **finbot_metadata}
    
    return Document(page_content=page_content, metadata=merged_metadata)

def add_to_vectorstore(lc_docs, collection_name):
    if not lc_docs:
        print("No documents to add to vector store.")
        return None
        
    else:
        print(f"\nAdding {len(lc_docs)} chunks to Qdrant vector store at /tmp/my_lang_vs under collection '{collection_name}'...")
        vectorstore = QdrantVectorStore.from_documents(
            documents=lc_docs,
            embedding=embeddings,
            path=settings.qdrant_path,
            collection_name=collection_name,
        )
        return vectorstore

def ingest_all_data(data_dir: str = "data"):
    """
    Recurisvely processes documents in the given data directory.
    Matches folders to RBAC collections and applies roles automatically.
    """
    base_path = Path(data_dir)
    if not base_path.exists():
        print(f"X Data directory '{base_path.absolute()}' does not exist! Please create it and add department folders.")
        return
        
    total_chunks_processed = 0
    
    for collection, roles in RBAC_MAPPING.items():
        collection_dir = base_path / collection
        if not collection_dir.exists():
            print(f"- Skipping '{collection}': folder {collection_dir} not found.")
            continue
            
        print(f"\n📁 Processing Collection: {collection} (Roles: {', '.join(roles)})")
        collection_chunks = []
        
        for file_path in collection_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in [".pdf", ".docx", ".doc", ".md", ".txt"]:
                print(f"  -> Parsing: {file_path.name}")
                try:
                    # 1. Parse Document with Docling structured parser
                    dl_docs = load_document(str(file_path))
                    
                    # 2. Map to Langchain Documents and strictly inject Metadata
                    for chunk in dl_docs:
                        lc_doc = enrich_langchain_doc(
                            lc_doc=chunk,
                            source=str(file_path),
                            collection=collection,
                            access_roles=roles
                        )
                        collection_chunks.append(lc_doc)
                except Exception as e:
                    print(f"  [Error] Failed to process {file_path.name}: {e}")
                    
        if collection_chunks:
            # We index this department's files directly into its own Qdrant collection
            add_to_vectorstore(collection_chunks, collection_name=collection)
            total_chunks_processed += len(collection_chunks)
            print(f"✅ Embedded {len(collection_chunks)} chunks into the '{collection}' collection!")
            
    if total_chunks_processed == 0:
        print("\n⚠️ No chunks were generated. Ensure there are documents inside the department folders.")
    else:
        print(f"\n🎉 Successfully ingested a total of {total_chunks_processed} chunks across all collections.")

if __name__ == "__main__":
    current_dir = Path(__file__).parent
    target_data_dir = current_dir / "data"
    ingest_all_data(str(target_data_dir))
    # print(target_data_dir)