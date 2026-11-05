import chromadb 
from chromadb.config import Settings as ChromaSettings

client = chromadb.PersistentClient(
    path= "data/vector_store" ,
    settings=ChromaSettings(anonymized_telemetry= False ),
) 
for col in client.list_collections():
    c = client.get_collection(col.name) 
    print (col.name, c.count()) 
    print('----------------\n')
    print (c.peek(limit= 23 )) # 查看前3条
    