using System;
using UnityEngine;
using UnityEngine.EventSystems;

namespace Manjong.UI
{
    /// <summary>
    /// Pointer handling for one tile of my hand (mouse and touch share the same uGUI events): a click selects, a
    /// horizontal drag past DragThreshold reorders. The owner receives pointer positions in the local space of
    /// "Space" (the hand area), so it never deals with screen scaling. A press that stays under the threshold is a
    /// click; once the threshold is crossed the click that uGUI still sends on release is swallowed.
    /// </summary>
    public class HandTileDrag : MonoBehaviour, IPointerDownHandler, IPointerClickHandler, IBeginDragHandler, IDragHandler, IEndDragHandler
    {
        /// <summary>Horizontal travel (UI units at the reference resolution) before a press counts as a drag.</summary>
        public const float DragThreshold = 12f;

        public int Index;
        /// <summary>Rect whose local coordinates are reported to the callbacks.</summary>
        public RectTransform Space;
        public Action<int> Clicked;
        /// <summary>(index, pointer position where the press started)</summary>
        public Action<int, Vector2> DragStarted;
        public Action<int, Vector2> Dragged;
        public Action<int, Vector2> DragEnded;

        Vector2 pressLocal;
        bool armed;
        bool dragActive;

        bool ToLocal(PointerEventData e, out Vector2 local)
        {
            local = Vector2.zero;
            if (Space == null) return false;
            return RectTransformUtility.ScreenPointToLocalPointInRectangle(Space, e.position, e.pressEventCamera, out local);
        }

        public void OnPointerDown(PointerEventData eventData)
        {
            armed = false;
            dragActive = false;
            Vector2 local;
            if (ToLocal(eventData, out local)) pressLocal = local;
        }

        public void OnPointerClick(PointerEventData eventData)
        {
            // uGUI sends the click before OnEndDrag; a real drag must not also select / discard the tile.
            if (dragActive) return;
            if (Clicked != null) Clicked(Index);
        }

        public void OnBeginDrag(PointerEventData eventData)
        {
            // Fires after EventSystem.pixelDragThreshold (a few px); our own, larger threshold is applied in OnDrag.
            armed = true;
        }

        public void OnDrag(PointerEventData eventData)
        {
            if (!armed) return;
            Vector2 local;
            if (!ToLocal(eventData, out local)) return;
            if (!dragActive)
            {
                if (Mathf.Abs(local.x - pressLocal.x) < DragThreshold) return;
                dragActive = true;
                if (DragStarted != null) DragStarted(Index, pressLocal);
            }
            if (Dragged != null) Dragged(Index, local);
        }

        public void OnEndDrag(PointerEventData eventData)
        {
            bool wasActive = dragActive;
            armed = false;
            dragActive = false;
            if (!wasActive) return;
            Vector2 local;
            if (!ToLocal(eventData, out local)) local = pressLocal;
            if (DragEnded != null) DragEnded(Index, local);
        }
    }
}
