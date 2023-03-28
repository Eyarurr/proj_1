# Скрипты для вской хуйни

Здесь лежат всякие скрипты, которые делаают какую-то работу, связанную с конкретными,
не повторяющимися задачами, но стирать их почему-то жаль.

Чтобы импортировать модули движка, начинать их нужно так:

    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    from visual.models import ...
    
    app = create_app('config.local.py')
    
    with app.app_context():
        # Тут вся полезная работа  
    
Или (что менее удобно и НЕ ПООЩРЯЕТСЯ) скармливать их содержимое на вход `py.py shell`.