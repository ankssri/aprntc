"""Hard gold set for the BytePlus support agent — the promotion-gate ruler.

Real questions about the BytePlus AI stack with reference answers + the doc area
that should ground them. Deliberately includes specific/edge-case questions where a
THIN parent (few chunks, terse prompt, no citation discipline) tends to be shallow,
incomplete, or uncited — i.e. genuine headroom for the apprentice.

Frozen + held-out: distillation must NEVER train on this.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GoldQA:
    question: str
    reference: str          # the key fact a good answer must contain
    expect_doc: str         # doc-area substring the answer should be grounded in
    must_cite: bool = True   # a good answer should cite a source


GOLD: tuple[GoldQA, ...] = (
    GoldQA("How do I enable deep reasoning in ModelArk?",
           "Set the thinking parameter type to enabled.",
           "Deepreasoning"),
    GoldQA("Where does the model's reasoning output appear in the response?",
           "In the reasoning_content field, separate from content.",
           "Deepreasoning"),
    GoldQA("What is VikingDB?",
           "A cloud vector database for storing, indexing, and searching massive vector data.",
           "Overview"),
    GoldQA("Which VikingDB index types are supported?",
           "HNSW, HNSW_HYBRID, FLAT, and DiskANN.",
           "Create Index"),
    GoldQA("How do I do hybrid dense-plus-sparse search in VikingDB?",
           "Pass both dense_vector and sparse_vector and tune dense_weight.",
           "Vector Search"),
    GoldQA("What is the upsert row limit per request in VikingDB?",
           "Up to 100 rows per request (1 if server-side vectorize is enabled).",
           "UpsertData"),
    GoldQA("How do I pass an image to the model for image understanding?",
           "As an image_url content part, by URL or base64 data URI.",
           "Image Understanding"),
    GoldQA("How is a video supplied to the video understanding API?",
           "As a video_url content part (URL or base64), with an optional fps.",
           "Video Understanding"),
    GoldQA("What signing method does the VikingDB API use?",
           "Volcengine Signature V4 (HMAC-SHA256) with service 'vikingdb'.",
           "Signature"),
    GoldQA("How do I get token usage when streaming a chat completion?",
           "Set stream_options.include_usage to true.",
           "Chat API"),
    GoldQA("What field carries tool calls in the chat completion response?",
           "The message.tool_calls field.",
           "Chat API"),
    GoldQA("How do I cap total output including the chain-of-thought?",
           "Use max_completion_tokens instead of max_tokens.",
           "Chat API"),
    GoldQA("How do I upload a file to use with the model?",
           "POST it to the Files API and reference the returned file id.",
           "FilesAPI"),
    GoldQA("How do I create a VikingDB collection's scalar filter?",
           "List the scalar fields in ScalarIndex when creating the index.",
           "Create Index"),
    GoldQA("What distance metrics does a VikingDB index support?",
           "Inner product (ip), L2, and cosine.",
           "Create Index"),
    GoldQA("How do I retrieve data by primary key in VikingDB?",
           "Use the fetch_in_collection / fetch data endpoint with ids.",
           "FetchData"),
    GoldQA("What is the base URL for ModelArk in the ap-southeast region?",
           "https://ark.ap-southeast.bytepluses.com/api/v3",
           "Chat API"),
    GoldQA("How does the model return streaming output?",
           "As SSE delta chunks ending with data: [DONE].",
           "Chat API"),
    GoldQA("What auth header does ModelArk use?",
           "Authorization: Bearer with your API key.",
           "Chat API"),
    GoldQA("How do I generate a video with Seedance?",
           "POST a generation task to the contents/generations/tasks endpoint.",
           "VideoGeneration"),
)
