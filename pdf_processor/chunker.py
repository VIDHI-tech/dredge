import re

def estimate_tokens(text):
    """
    Estimate token count based on character count.
    Roughly 1 token ~= 4 characters for English text.
    """
    return len(text) // 4

def chunk_text(text, chunk_size=3000, overlap=200):
    """
    Splits text into chunks of approximately `chunk_size` tokens.
    
    Args:
        text (str): Text to chunk.
        chunk_size (int): Target tokens per chunk.
        overlap (int): Token overlap between chunks.
    
    Returns:
        list of str: List of text chunks.
    """
    if not text:
        return []

    # Rough character mapping
    char_chunk_size = chunk_size * 4
    char_overlap = overlap * 4

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + char_chunk_size
        
        # If we are not at the end, try to break at a sentence or paragraph
        if end < text_len:
            # Look for double newline (paragraph break) within the last 20% of the chunk
            search_start = max(start, end - int(char_chunk_size * 0.2))
            # Try paragraph break first
            paragraph_break = text.rfind('\n\n', search_start, end)
            if paragraph_break != -1:
                end = paragraph_break + 2 # Include the newlines
            else:
                # Try sentence break (. followed by space/newline)
                sentence_break = -1
                match = re.search(r'\.\s+', text[search_start:end])
                if match:
                    # re.search returns index relative to snippet, so adjust
                    sentence_break = search_start + match.end()
                
                if sentence_break != -1:
                    end = sentence_break
                else:
                    # Fallback to space
                    space_break = text.rfind(' ', search_start, end)
                    if space_break != -1:
                        end = space_break + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # Move start forward, backing up by overlap
        start = end - char_overlap
        
        # Ensure we always make progress
        if start >= end:
             start = end - char_overlap # Should verify logic

        # Strict progress check to avoid infinite loops if overlap >= chunk_size or similar
        if start <= (end - char_chunk_size):
             start = end 

    return chunks
