from django.contrib.auth.base_user import BaseUserManager

class UserManager(BaseUserManager):
    use_in_migrations = True

    def normalize_phone(self, phone: str):
        if not phone:
            return phone
        p = ''.join(ch for ch in phone if ch.isdigit() or ch == '+')
        if p.startswith('998'):
            p = '+{}'.format(p)
        if not p.startswith('+'):
            # assume Uzbekistan if 9-12 digits provided (dev convenience)
            if len(p) == 12 and p.startswith('998'):
                p = f'+{p}'
        return p

    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError('Phone is required')
        phone = self.normalize_phone(phone)
        user = self.model(phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(phone, password, **extra_fields)