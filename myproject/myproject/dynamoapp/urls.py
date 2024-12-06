from django.urls import path
from .views import add_item,read_all_items,update_item,delete_item

urlpatterns = [
    path('', add_item, name='add-item'),
    path('add-item/', add_item, name='add-item'),
    path('read_all_items/', read_all_items, name='read_all_items'),
    path('update_item/', update_item, name='update_item'),
     path('delete_item/', delete_item, name='delete_item'),
]
    