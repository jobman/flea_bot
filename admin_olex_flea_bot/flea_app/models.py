from django.db import models

# Create your models here.
class Profile(models.Model):
    external_id = models.PositiveIntegerField(
        verbose_name='ID пользователя в Telegram',
        unique=True,
    )
    username = models.TextField(
        verbose_name='Ник в Telegram'
    )

    is_admin = models.BooleanField(
        verbose_name='Администратор',
        default=False,
    )

    def __str__(self):
        return f'@{self.username} #{self.external_id}'

    class Meta:
        verbose_name = 'Профиль'
        verbose_name_plural = 'Профили'


class Post(models.Model):
    profile = models.ForeignKey(
        to='flea_app.Profile',
        verbose_name='Профиль',
        on_delete=models.PROTECT,
    )
    external_id = models.PositiveIntegerField(
        verbose_name='ID в Барахолке',
        null=True,

    )

    price = models.TextField(
        verbose_name='Цена',
        null=True,
    )

    text = models.TextField(
        verbose_name='Описание',
    )

    type_p = models.TextField(
        verbose_name='Тип поста'
    )

    image_file_id = models.TextField(
        verbose_name='Фото',
        null=True,
    )

    created_at = models.DateTimeField(
        verbose_name='Время получения',
        auto_now_add=True,
    )

    reviewed_at = models.DateTimeField(
        verbose_name='Время рассмотрения',
        null=True,
    )

    class Status(models.TextChoices):
        ON_REVIEW = (1, 'На рассмотрении')
        APPROVED = (2, 'Подтверждено')
        DECLINE = (3, 'Отклонено')
        WAIT_MONEY = (4, 'Ожидает оплаты')
        SOLD = (5, 'Продано')
        ON_CREATE = (6, 'Создается')

    status = models.CharField(
        verbose_name='Статус',
        max_length=20,
        choices=Status.choices,
        default=Status.ON_REVIEW,
    )

    def __str__(self):
        return f'Сообщение #{self.external_id} от {self.profile}'

    class Meta:
        verbose_name = 'Пост'
        verbose_name_plural = 'Посты'
