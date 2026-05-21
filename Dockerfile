FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Run interactively so the user can answer prompts
CMD ["python", "-u", "main.py"]
