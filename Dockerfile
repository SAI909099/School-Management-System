FROM python:3.10

RUN apt update && apt install -y build-essential

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# collect static files into /app/staticfiles
RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "school_project.wsgi:application", "--bind", "0.0.0.0:8000"]
