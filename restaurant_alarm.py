def calculate_meal_total():
    """Calculates the total cost of a meal with tax and tip."""
    try:
        food_charge = float(input("Enter the charge for the food: $"))
        tip = food_charge * 0.18  # 18% tip
        tax = food_charge * 0.07  # 7% sales tax
        total_price = food_charge + tip + tax
        
        print("\n--- Meal Cost Breakdown ---")
        print(f"Food Charge: ${food_charge:.2f}")
        print(f"Tip (18%): ${tip:.2f}")
        print(f"Sales Tax (7%): ${tax:.2f}")
        print(f"Total Price: ${total_price:.2f}\n")
    except ValueError:
        print("Invalid input. Please enter a numeric value.")


def alarm_clock():
    """Calculates what time it will be after a given waiting period."""
    try:
        current_time = int(input("Enter the current time (0-23 hours): "))
        hours_to_wait = int(input("Enter the number of hours to wait: "))
        
        if 0 <= current_time < 24 and hours_to_wait >= 0:
            new_time = (current_time + hours_to_wait) % 24
            print(f"\nIn {hours_to_wait} hours, the time will be {new_time}:00 on a 24-hour clock.\n")
        else:
            print("Invalid input. Please enter a time between 0 and 23 and a non-negative wait period.")
    except ValueError:
        print("Invalid input. Please enter integer values.")


if __name__ == "__main__":
    print("Welcome to the Meal Calculator and Alarm Clock Program!\n")
    
    # Execute meal total calculation
    calculate_meal_total()
    
    # Execute alarm clock calculation
    alarm_clock()
    
    print("\nThank you for using the program!")