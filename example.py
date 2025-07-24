#!/usr/bin/env python3
from llm_converter import FileConverter


file_path = "sample_documents/invoice.pdf"

converter = FileConverter(
    # cloud_mode=True,
    # api_key="<api-key>"
)

# # # Standard conversions
# # result = converter.convert(file_path).to_csv()
# # print("📝=============================== CSV Output:===============================")
# # print(result)

# # result = converter.convert(file_path).to_html()
# # print("📝=============================== HTML Output:===============================")
# # print(result)

print("📝=============================== JSON Output:===============================")
result = converter.convert(file_path).to_json()
print(result)

# Intelligent field extraction examples (works with both cloud and local modes)
print("\n📝=============================== Intelligent Field Extraction:===============================")

# Example 1: Extract specific fields
result = converter.convert(file_path)
try:
    specific_fields = result.to_json(specified_fields=[
        "total_amount", 
        "date", 
        "vendor_name",
        "invoice_number"
    ])
    print("Specific fields extraction:")
    print(specific_fields)
except Exception as e:
    print(f"Field extraction failed: {e}")

print("\n" + "="*80 + "\n")

# Example 2: Extract using JSON schema
try:
    schema = {
        "invoice_number": "string",
        "total_amount": "number",
        "vendor_name": "string", 
        "items": [{
            "description": "string",
            "amount": "number"
        }]
    }
    
    structured_data = result.to_json(json_schema=schema)
    print("JSON schema extraction:")
    print(structured_data)
except Exception as e:
    print(f"Schema extraction failed: {e}")

result = converter.convert(file_path).to_text()

print("📝=============================== Markdown Output:===============================")
print(result)
