import os
import re
from collections import Counter

DATA_DIR = "data/bytedance"

# Common tech keywords to look for (extensible)
KEYWORDS = [
    "Python", "Java", "Go", "Golang", "C\+\+", "C#", "Rust", "JavaScript", "TypeScript", 
    "React", "Vue", "Angular", "Node", "Spring", "Django", "Flask", "Gin",
    "Kotlin", "Swift", "Objective-C", "Flutter",
    "MySQL", "PostgreSQL", "MongoDB", "Redis", "Elasticsearch", "Kafka", "RocketMQ",
    "Docker", "Kubernetes", "K8s", "Linux", "Git", "CI/CD",
    "Spark", "Hadoop", "Flink", "Hive", "PyTorch", "TensorFlow", "Keras", "LLM", "NLP", "CV", "Multimodal"
]

def analyze_tech_stack():
    counter = Counter()
    total_files = 0
    
    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".md"):
            total_files += 1
            path = os.path.join(DATA_DIR, filename)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Normalize content
            content_lower = content.lower()
            
            for keyword in KEYWORDS:
                # Use word boundary to avoid partial matches (e.g. "Go" in "Good")
                # For "C++", skip regex word boundary on right or handle specifically
                if keyword == "C\+\+":
                    pattern = r"c\+\+"
                elif keyword == "C#":
                    pattern = r"c#"
                else:
                    pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
                
                if re.search(pattern, content_lower):
                    # Store original case for display
                    display_key = keyword.replace("\\", "") 
                    if display_key == "Golang": display_key = "Go" # Merge Go/Golang
                    counter[display_key] += 1
                    
    print(f"Analyzed {total_files} job postings.")
    print("\nTop Tech Stack Mentions:")
    for tech, count in counter.most_common():
        percentage = (count / total_files) * 100
        print(f"- {tech}: {count} ({percentage:.1f}%)")

if __name__ == "__main__":
    analyze_tech_stack()
