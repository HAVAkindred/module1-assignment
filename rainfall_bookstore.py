# Part 1: Average Rainfall Calculation
num_years = int(input("Enter the number of years: "))
total_rainfall = 0
total_months = num_years * 12

for year in range(1, num_years + 1):
    for month in range(1, 13):
        rainfall = float(input(f"Enter rainfall (in inches) for Year {year}, Month {month}: "))
        total_rainfall += rainfall

average_rainfall = total_rainfall / total_months

print(f"\nTotal months: {total_months}")
print(f"Total inches of rainfall: {total_rainfall:.2f}")
print(f"Average rainfall per month: {average_rainfall:.2f} inches")

# Part 2: Bookstore Points System
num_books = int(input("\nEnter the number of books purchased this month: "))

if num_books == 0:
    points = 0
elif num_books == 2:
    points = 5
elif num_books == 4:
    points = 15
elif num_books == 6:
    points = 30
elif num_books >= 8:
    points = 60
else:
    points = 0  # Default case if the number is outside specified range

print(f"You have earned {points} points.")

# Keep the window open if run by double-clicking
input("\nPress Enter to exit...")
