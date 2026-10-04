# booking_reminder_day_before — UTILITY

The reply matters: a "yes" back is caught by aftercare.py and marks the booking
confirmed, which is what feeds the owner's morning no-show list. So the body has
to actually ask for a yes — not just "reply if you need to change".

## English
Body:
Hi {{1}}, reminder of your appointment at {{2}} tomorrow at {{3}} for {{4}}.
Reply YES to confirm, or tell us here if you need to change the time.

Vars: 1=customer name, 2=garage name, 3=time, 4=service
Sample: Ahmed | Care Auto Repair | 10:30 AM | brake pads replacement

## Arabic
مرحباً {{1}}، تذكير بموعدك في {{2}} غداً الساعة {{3}} لخدمة {{4}}.
ردّ بكلمة "نعم" للتأكيد، أو أخبرنا هنا إذا رغبت في تغيير الموعد.

## Hindi
नमस्ते {{1}}, आपका अपॉइंटमेंट {{2}} में कल {{3}} बजे {{4}} के लिए है।
पक्का करने के लिए YES लिखें, या समय बदलना हो तो यहीं जवाब दें।

## Urdu
{{1}} صاحب، {{2}} میں کل {{3}} بجے {{4}} کے لیے آپ کا اپائنٹمنٹ ہے۔
تصدیق کے لیے YES لکھیں، یا وقت بدلنا ہو تو یہیں جواب دیں۔
