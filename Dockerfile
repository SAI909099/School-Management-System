FROM python:3.10

# Create working directory
WORKDIR /app

# Install system deps
RUN apt update && apt install -y build-essential

# Copy requirements
COPY requirements.txt .

# Install python deps
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project
COPY . .

# Expose Django/Gunicorn port
EXPOSE 8000

# Run Gunicorn
CMD ["gunicorn", "school_project.wsgi:application", "--bind", "0.0.0.0:8000"]
