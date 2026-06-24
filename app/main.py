from fastapi import FastAPI

app = FastAPI(title="AI Transaction Pipeline")

@app.get("/")
def root():
    return {"message": "API Running"}

@app.get("/health")
def health():
    return {"status": "ok"}